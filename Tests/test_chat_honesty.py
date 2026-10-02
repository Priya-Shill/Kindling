"""
The chat must never hand a student a made-up career list.

Found in live testing: a thread whose 7 intake answers were too short
to score dropped into open mentor chat anyway, with no scores and no
Career Graph. Asked "isn't there a career path for me yet?", the
mentor prompt answered with a plausible list of careers from general
knowledge - indistinguishable, to the student, from a real result.
That thread could also never be scored afterwards, however much the
student went on to say.

Every AI call is mocked; no network. Run from the repo root.
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

SCORES = {"builds_tinkers": 0.1, "investigates_why": 0.2, "creates_expresses": 0.7,
          "works_with_people": 0.1, "organizes_systems": 0.1, "leads_persuades": 0.1}
TOO_SHORT = ["photos", "Both", "yes", "idk", "alone", "not sure", "ok"]
CAREER_QUESTION = "isn't there a career path for me yet?"
DETAILED = "i take portraits of my cousins near the window because soft light makes faces look calm"


class ChatCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        db.init_db()
        cls.client = TestClient(main.app)
        email = f"test-honesty-{os.urandom(4).hex()}@example.com"
        r = cls.client.post("/api/auth/signup", json={"email": email, "password": "testpass123"})
        assert r.status_code == 200, r.text
        cls.token = r.json()["token"]
        cls.session_ids = []

    @classmethod
    def tearDownClass(cls):
        conn = db.get_db()
        for sid in cls.session_ids:
            for table in ("messages", "events", "sessions"):
                conn.execute(f"DELETE FROM {table} WHERE session_id = ?", (sid,))
        conn.execute("DELETE FROM users WHERE id = ?", (cls.token,))
        conn.commit()
        conn.close()

    def setUp(self):
        r = self.client.post("/api/chat/start", json={"token": self.token})
        self.sid = r.json()["session_id"]
        self.session_ids.append(self.sid)
        self.prompts = []          # every system prompt an LLM call was made with
        self.scored = []           # every transcript handed to the scorer

        def fake_llm(messages, system_prompt="", temperature=None):
            self.prompts.append(system_prompt)
            if system_prompt.startswith(main.PHASE2_SYSTEM_PROMPT):
                return "MENTOR REPLY"
            return "INTAKE QUESTION?"

        def fake_score(messages):
            self.scored.append(messages)
            return dict(SCORES)

        patches = [
            patch.object(main, "call_llm", fake_llm),
            patch.object(main, "score_session", fake_score),
            patch.object(main, "generate_title", lambda messages: "Photos"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def say(self, text, **extra):
        r = self.client.post("/api/chat/message", json={
            "session_id": self.sid, "token": self.token, "message": text, **extra})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def used_mentor_prompt(self):
        return any(p.startswith(main.PHASE2_SYSTEM_PROMPT) for p in self.prompts)


class TestNoResultsYet(ChatCase):

    def test_career_question_mid_intake_gets_the_honest_answer(self):
        self.say("photography i guess")
        self.say("Both")
        r = self.say(CAREER_QUESTION)

        self.assertTrue(r["reply"].startswith(main.NO_RESULTS_YET_MESSAGE))
        self.assertTrue(r["reply"].endswith("INTAKE QUESTION?"))
        self.assertFalse(r["intake_complete"])
        self.assertFalse(self.used_mentor_prompt())

    def test_unscored_thread_never_reaches_the_mentor_prompt(self):
        for text in TOO_SHORT:
            r = self.say(text)
        # The 7th answer: coached once, and the conversation carries on.
        self.assertTrue(r["reply"].startswith(main.INSUFFICIENT_CONTENT_MESSAGE))
        self.assertTrue(r["reply"].endswith("INTAKE QUESTION?"))
        self.assertFalse(r["intake_complete"])
        self.assertEqual(self.scored, [])

        r = self.say(CAREER_QUESTION)
        self.assertTrue(r["reply"].startswith(main.NO_RESULTS_YET_MESSAGE))
        self.assertEqual(r["question_index"], main.TOTAL_PHASE1_QUESTIONS)

        r = self.say("ok")
        self.assertEqual(r["reply"], "INTAKE QUESTION?", "the coaching message is not repeated every turn")

        self.assertFalse(self.used_mentor_prompt())
        self.assertEqual(self.scored, [], "asking about careers must not count as evidence")
        self.assertIsNone(db.get_latest_inference_scores(self.sid))

    def test_thread_recovers_as_soon_as_there_is_enough(self):
        for text in TOO_SHORT:
            self.say(text)
        self.say(CAREER_QUESTION)

        r = self.say(DETAILED)
        self.assertTrue(r["intake_complete"])
        self.assertEqual(r["reply"], main.CLOSING_MESSAGE)
        self.assertEqual(len(self.scored), 1)
        self.assertIsNotNone(db.get_latest_inference_scores(self.sid))

        r = self.say("how do i get sharper eyes in a portrait?")
        self.assertEqual(r["reply"], "MENTOR REPLY")
        self.assertGreater(r["question_index"], main.TOTAL_PHASE1_QUESTIONS)

    def test_brief_but_genuine_answers_are_enough(self):
        for text in ["photography i guess", "Both", "soft lighting", "yes", "portraits", "alone", "not sure"]:
            r = self.say(text)
        self.assertTrue(r["intake_complete"])
        self.assertEqual(len(self.scored), 1)

    def test_session_history_reports_whether_the_intake_is_done(self):
        for text in TOO_SHORT:
            self.say(text)
        self.say("ok")
        r = self.client.get(f"/api/chat/session/{self.sid}", params={"token": self.token}).json()
        self.assertIs(r["intake_complete"], False)
        self.say(DETAILED)
        r = self.client.get(f"/api/chat/session/{self.sid}", params={"token": self.token}).json()
        self.assertIs(r["intake_complete"], True)


class TestWithRealResults(ChatCase):

    def scored_thread(self):
        for i in range(7):
            self.say(f"i take portraits near the window because soft light looks calm, part {i}")
        self.prompts.clear()

    def test_results_note_is_added_only_when_asked(self):
        self.scored_thread()
        self.say("how do i get sharper eyes in a portrait?")
        self.assertNotIn("REAL RESULTS\n", self.prompts[-1])

        self.say("so what careers fit me?")
        self.assertIn("REAL RESULTS\n", self.prompts[-1])
        self.assertIn("Do not name any careers as their matches", self.prompts[-1])

    def test_results_note_lists_only_the_real_graph(self):
        self.scored_thread()
        key = f"{self.sid}_test"
        main.CAREER_TREE_CACHE[key] = {"nodes": [
            {"id": "you", "type": "hub", "label": "You"},
            {"id": "o:27-4021.00", "type": "career", "label": "Photographers", "fullTitle": "Photographers"},
        ], "edges": []}
        self.addCleanup(main.CAREER_TREE_CACHE.pop, key, None)

        self.say("which careers suit me?")
        note = self.prompts[-1].split("REAL RESULTS\n", 1)[1]
        self.assertIn("Photographers", note)
        self.assertIn("Do not add careers of your own", note)

    def test_nudge_towards_results_is_occasional(self):
        self.scored_thread()
        replies = [self.say(f"another thought number {i}")["reply"] for i in range(1, 13)]
        nudged = [i for i, reply in enumerate(replies, start=1) if reply != "MENTOR REPLY"]
        self.assertEqual(nudged, [main.NUDGE_EVERY, 2 * main.NUDGE_EVERY])
        for i in nudged:
            self.assertTrue(replies[i - 1].startswith("MENTOR REPLY\n\n"))
            self.assertIn("Career Graph", replies[i - 1])


class TestHelpers(unittest.TestCase):

    def test_career_match_questions(self):
        for text in [CAREER_QUESTION, "so what careers fit me?", "what should i become?",
                     "which job suits me", "any directions for me?"]:
            with self.subTest(text=text):
                self.assertTrue(main.is_career_match_question(text))
        for text in ["my dad has a boring job", "what is a choreographer?", "Both",
                     "how do people get into work as dancers?", "i like taking photos of my cousins"]:
            with self.subTest(text=text):
                self.assertFalse(main.is_career_match_question(text))

    def test_evidence_gate_counts_distinct_content_words(self):
        count = main.evidence_word_count
        self.assertEqual(count(["idk", "nothing much", "ok", "maybe", "yes", "no", "not sure"]), 0)
        self.assertEqual(count(["the the the and you", "dance dance dance"]), 1)
        self.assertEqual(count(["F1 and AI"]), 2)
        self.assertGreaterEqual(
            count(["photography i guess", "Both", "soft lighting", "yes", "portraits", "alone", "not sure"]),
            main.MIN_EVIDENCE_WORDS)
        self.assertLess(count(TOO_SHORT), main.MIN_EVIDENCE_WORDS)

    def test_reply_rules_no_longer_prescribe_one_shape(self):
        self.assertNotIn("Structure every reply the same way", main.PHASE2_SYSTEM_PROMPT)
        self.assertIn("There is no template", main.PHASE2_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
