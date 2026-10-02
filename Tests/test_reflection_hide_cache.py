"""
Regression test for the "Your take" hide bug (third report of it):
hiding a career from Reflection never actually removed it from the
Career Graph, and un-hiding it never actually brought it back either.

Root cause: CAREER_TREE_CACHE (backend/main.py) keys only on
session_id + a hash of that session's scores. Reflection preferences
are stored per-user and change neither of those, so a save/delete of
a hide preference never invalidated the cached tree - the same stale,
pre-preference tree kept being served indefinitely, on every thread
that user had, until the scores happened to change for some unrelated
reason.

Every real AI call (tree_enrichment.py's short-title/why/try-it
generation, and the reflection note's own extraction call) is mocked,
per instruction, so this runs fast and deterministically with no real
LLM calls, no network, and no dependence on what a live model happens
to say on a given run.
"""

import os
import sys
import unittest
from unittest.mock import patch

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "Scripts"))

from fastapi.testclient import TestClient
from backend import main, db

# backend/main.py appends BACKEND_DIR to sys.path and imports several
# of its own collaborators as BARE top-level modules (e.g. "from
# tree_enrichment import enrich_tree_with_ai", not a package-relative
# import). Because this test file ALSO puts backend/ on sys.path,
# `import tree_enrichment` here resolves to a SEPARATE module object
# in sys.modules than `backend.tree_enrichment` would - patching the
# wrong one silently never affects what backend.main actually calls.
# Importing the bare names directly and patching those exact objects
# (via patch.object, never a string target) keeps this unambiguous.
import tree_enrichment


def _mock_short_title(full_title):
    return full_title[:24]


def _mock_why_connected(occupation_title, occupation_description, user_evidence, pattern_label):
    # relevant=True so candidates actually survive _prune_irrelevant_
    # careers (backend/tree_enrichment.py) - this test session has no
    # real evidence text at all (scores are seeded directly, no chat
    # ever happened), so the real relevance filter would honestly
    # prune every single candidate otherwise. This test is about cache
    # invalidation, not match quality, so a fixed "relevant" stub is
    # the right fake here, not a realistic evidence-based judgment.
    return f"Connected to the {pattern_label} pattern.", True


def _mock_try_it(occupation_title, task_text):
    return "Try a small version of this task yourself."


class TestReflectionHideInvalidatesCareerTreeCache(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        db.init_db()
        cls.client = TestClient(main.app)

        email = f"test-hide-cache-{os.urandom(4).hex()}@example.com"
        r = cls.client.post("/api/auth/signup", json={"email": email, "password": "testpass123"})
        assert r.status_code == 200, r.text
        cls.token = r.json()["token"]

        r = cls.client.post("/api/chat/start", json={"token": cls.token})
        assert r.status_code == 200, r.text
        cls.session_id = r.json()["session_id"]

        # "why_connected" is cached in the generated_strings table by
        # soc+evidence_hash, where evidence_hash is a hash of this
        # session's real user message text. A session with ZERO user
        # messages (true of every session this test's approach would
        # otherwise create) hashes to the exact same constant key every
        # run, across every test run that ever did this - so a single
        # earlier UNMOCKED run poisons that cache entry with a real,
        # correctly-honest "relevant: false" (empty evidence really
        # doesn't connect to anything), and every later run - even a
        # properly mocked one - silently inherits that stale verdict
        # from the DB cache, never reaching the mock at all. A real,
        # unique message sidesteps this entirely.
        db.add_message(cls.session_id, "user", f"test evidence token {os.urandom(8).hex()}")

        # Seed real scores directly - Phase 1's own scoring call isn't
        # what this test is about, and this keeps the test from needing
        # 7 real chat turns or a real score_session() LLM call at all.
        # works_with_people dominant reliably surfaces real, cacheable
        # candidates to hide.
        db.log_event(cls.session_id, "score_computed", {
            "scores": {
                "builds_tinkers": 0.1, "investigates_why": 0.2, "creates_expresses": 0.2,
                "works_with_people": 0.9, "organizes_systems": 0.3, "leads_persuades": 0.3,
            },
            "scored_at_message_count": 7,
        })

    @classmethod
    def tearDownClass(cls):
        conn = db.get_db()
        conn.execute("DELETE FROM messages WHERE session_id = ?", (cls.session_id,))
        conn.execute("DELETE FROM events WHERE session_id = ?", (cls.session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (cls.session_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (cls.token,))
        conn.commit()
        conn.close()

    def _patched_ai_calls(self):
        # The generated-string cache is swapped for an in-memory one
        # too: short titles and "try it" text are cached by occupation
        # and task alone, shared by every user, so writing these mocks
        # to the real table left "Try a small version of this task
        # yourself." showing on real careers in the local app.
        fake_cache = {}
        return patch.multiple(
            tree_enrichment,
            generate_career_short_title=_mock_short_title,
            generate_why_connected=_mock_why_connected,
            generate_try_it=_mock_try_it,
            get_cached_string=fake_cache.get,
            set_cached_string=lambda key, kind, value: fake_cache.__setitem__(key, value),
        )

    def _career_labels(self):
        r = self.client.get(f"/api/career-tree/{self.session_id}", params={"token": self.token})
        self.assertEqual(r.status_code, 200, r.text)
        return [n["label"] for n in r.json()["nodes"] if n["type"] == "career"], r.json()

    def test_hide_then_restore_round_trip(self):
        with self._patched_ai_calls():
            labels_before, tree_before = self._career_labels()
            self.assertTrue(labels_before, "need at least one real candidate career to hide")
            target_label = labels_before[0]
            target_soc = next(
                n["soc"] for n in tree_before["nodes"]
                if n["type"] == "career" and n["label"] == target_label
            )

            # Mock the note's own extraction call - the LLM step this
            # test isn't about - to deterministically name the real
            # node we just confirmed exists in this student's own tree.
            # patch.object(main, ...) targets the exact module object
            # this test already imported and that TestClient(main.app)
            # actually runs - not a same-named-but-different module a
            # string target could resolve to instead (see the import
            # comment above for tree_enrichment's identical pitfall).
            with patch.object(main, "extract_reflection_note", return_value={
                "hideFields": [target_label],
                "focusField": None,
                "goDeeper": False,
                "newToThem": [],
                "patternAdjustments": [],
            }):
                r = self.client.post("/api/reflection/note", json={
                    "token": self.token,
                    "session_id": self.session_id,
                    "note_text": f"I'd rather not see {target_label} as an option.",
                })
            self.assertEqual(r.status_code, 200, r.text)
            prefs = r.json()["note"]["preferences"]
            self.assertEqual(len(prefs), 1, f"expected the hide to resolve to a real node: {r.json()}")
            self.assertEqual(prefs[0]["kind"], "hide_field")
            pref_id = prefs[0]["id"]

            # The stored preference must key off the real SOC code, not
            # just the display label (which can change if it's later
            # re-generated).
            stored_pref = db.get_reflection_preference(pref_id)
            self.assertEqual(stored_pref["extra"].get("soc"), target_soc)

            # The hidden career must be gone from the very next fetch -
            # this is the exact assertion that failed before the cache
            # invalidation fix (same session_id, same scores, so the
            # old cache_key logic kept serving the pre-hide tree).
            labels_after_hide, _ = self._career_labels()
            self.assertNotIn(target_label, labels_after_hide)

            # Removing the chip (deleting the preference) must bring it
            # back on the very next fetch.
            r = self.client.delete(f"/api/reflection/preference/{pref_id}", params={"token": self.token})
            self.assertEqual(r.status_code, 200, r.text)

            labels_after_restore, _ = self._career_labels()
            self.assertIn(target_label, labels_after_restore)


if __name__ == "__main__":
    unittest.main()
