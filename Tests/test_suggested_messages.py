"""
Regression test for the "Leads & persuades jumped with no evidence"
report.

Root cause: the debounced Phase 2 rescore (backend/main.py's
maybe_rescore_session) scored every user message as the student's own
words, including the ones a button sent for them - e.g. Career Graph's
"I want to try this small task: Direct rehearsals to instruct
dancers..." is an O*NET task statement. Two button clicks were enough
to trigger a rescore, and that text alone moved leads_persuades from
0.05 to 0.70 for a student who had only described dancing alone.

Every real AI call is mocked, so this runs with no network.
"""

import os
import sys
import unittest
from unittest.mock import patch

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "Scripts"))
sys.path.insert(0, os.path.join(ROOT_DIR, "ai_core"))

from fastapi.testclient import TestClient
from backend import main, db

BUTTON_TASK = ("I want to try this small task: Direct rehearsals to instruct dancers "
               "in dance steps. Can you walk me through it?")
BUTTON_QUESTION = "How do people get into work as choreographers?"

FLAT_SCORES = {
    "builds_tinkers": 0.1, "investigates_why": 0.3, "creates_expresses": 0.9,
    "works_with_people": 0.1, "organizes_systems": 0.2, "leads_persuades": 0.05,
}


class TestSuggestedMessagesAreNotEvidence(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        db.init_db()
        cls.client = TestClient(main.app)

        email = f"test-suggested-{os.urandom(4).hex()}@example.com"
        r = cls.client.post("/api/auth/signup", json={"email": email, "password": "testpass123"})
        assert r.status_code == 200, r.text
        cls.token = r.json()["token"]

        r = cls.client.post("/api/chat/start", json={"token": cls.token})
        cls.session_id = r.json()["session_id"]

    @classmethod
    def tearDownClass(cls):
        conn = db.get_db()
        conn.execute("DELETE FROM messages WHERE session_id = ?", (cls.session_id,))
        conn.execute("DELETE FROM events WHERE session_id = ?", (cls.session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (cls.session_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (cls.token,))
        conn.commit()
        conn.close()

    def _send(self, text, suggested=False):
        body = {"session_id": self.session_id, "token": self.token, "message": text}
        if suggested:
            body["suggested"] = True
        r = self.client.post("/api/chat/message", json=body)
        self.assertEqual(r.status_code, 200, r.text)

    def _get_inference(self):
        r = self.client.get(f"/api/chat/inference/{self.session_id}", params={"token": self.token})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["inference"]

    def test_button_messages_never_reach_scoring(self):
        scored_transcripts = []

        def fake_score(messages):
            scored_transcripts.append(messages)
            return dict(FLAT_SCORES)

        with patch.object(main, "score_session", fake_score), \
             patch.object(main, "call_llm", lambda **kwargs: "What draws you to that?"), \
             patch.object(main, "generate_title", lambda messages: "Dancing"):

            for i in range(7):
                self._send(f"i practise contemporary dance alone in my room every evening, part {i}")
            self.assertEqual(len(scored_transcripts), 1)

            # Two button-sent prompts: enough messages to pass the old
            # debounce, but none of it is the student's own evidence.
            self._send(BUTTON_TASK, suggested=True)
            self._send(BUTTON_QUESTION, suggested=True)
            self._get_inference()
            self.assertEqual(len(scored_transcripts), 1, "button prompts alone triggered a rescore")

            # Two typed messages do trigger one - without the button text in it.
            self._send("ok. what styles are there besides contemporary?")
            self._send("i think i'd like to try hip hop next")
            self._get_inference()
            self.assertEqual(len(scored_transcripts), 2)

            scored_text = "\n".join(m["content"] for m in scored_transcripts[-1])
            self.assertNotIn("Direct rehearsals", scored_text)
            self.assertNotIn(BUTTON_QUESTION, scored_text)
            self.assertIn("hip hop", scored_text)

        # The chat itself still shows everything the student saw.
        full = "\n".join(m["content"] for m in db.get_messages(self.session_id))
        self.assertIn("Direct rehearsals", full)

    def test_not_quite_changes_only_the_clicked_pattern(self):
        sid = db.create_session(user_id=self.token)
        try:
            db.add_message(sid, "user", "seed")
            db.log_event(sid, "score_computed", {"scores": dict(FLAT_SCORES), "scored_at_message_count": 7})

            r = self.client.post("/api/user/trait/decision", json={
                "session_id": sid, "token": self.token, "trait": "investigates_why", "action": "reject",
            })
            self.assertEqual(r.status_code, 200, r.text)

            after = db.get_latest_inference_scores(sid)
            self.assertEqual(after["investigates_why"], 0.0)
            for trait, value in FLAT_SCORES.items():
                if trait != "investigates_why":
                    self.assertEqual(after[trait], value, trait)

            r = self.client.post("/api/user/trait/decision", json={
                "session_id": sid, "token": self.token, "trait": "creates_expresses", "action": "accept",
            })
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(db.get_latest_inference_scores(sid), after)
        finally:
            conn = db.get_db()
            conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
            conn.execute("DELETE FROM events WHERE session_id = ?", (sid,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))
            conn.commit()
            conn.close()


if __name__ == "__main__":
    unittest.main()
