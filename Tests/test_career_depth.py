"""
Career Graph depth: "Show more" layers, "Where this work happens" and
"Ways people specialise".

The rule these protect: every occupation on the graph is a real one
from the O*NET dataset. "Show more" only ever returns dataset
occupations, and the one AI-generated feature (career depth) returns
panel text and example specialisations - never an occupation.

Every AI call is mocked; no network. Run from the repo root.
"""

import json
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
import career_tree
from career_depth import validate_depth
from soc_titles import minor_group

with open(os.path.join(ROOT_DIR, "Outputs", "career_graph.json"), encoding="utf-8") as f:
    OCCUPATIONS = json.load(f)
REAL_IDS = {occ["id"] for occ in OCCUPATIONS}
ID_BY_TITLE = {occ["title"]: occ["id"] for occ in OCCUPATIONS}

SCORES = {"builds_tinkers": 0.1, "investigates_why": 0.2, "creates_expresses": 0.85,
          "works_with_people": 0.1, "organizes_systems": 0.4, "leads_persuades": 0.05}
EVIDENCE = [
    "dancing. i've been learning contemporary from youtube videos in my room",
    "the movement i think, how you can show a feeling with just your body",
    "alone mostly. i like practising by myself until a move feels right",
    "i replay the same 8 counts again and again until the timing is right",
    "my flexibility and turns, and remembering long routines",
    "sometimes i mix moves from different videos into my own little routine",
    "maybe hip hop, it looks fun but harder",
]

GOOD_DEPTH = {
    "workplaces": [
        {"setting": "Dance companies and troupes", "examples": ["Nritarutya", "The Royal Ballet", "A third one"]},
        {"setting": "Film and television", "examples": []},
        {"setting": "Dance schools", "examples": ["Shiamak Davar's Institute"]},
    ],
    "specialisations": [
        {"name": "Ballet", "about": "A classical style built on precise technique."},
        {"name": "Hip-hop", "about": "A street style built on rhythm and improvisation."},
        {"name": "Kathak", "about": "A North Indian classical style known for fast footwork and spins."},
    ],
}


def first_view():
    tree = career_tree.build_career_tree_core(SCORES, {}, frozenset(), frozenset(), [], "\n".join(EVIDENCE))
    careers = [n for n in tree["nodes"] if n["type"] == "career"]
    fields = [n for n in tree["nodes"] if n["type"] == "field"]
    return tree, careers, fields


def more(node_id, shown, field_ids, hidden_ids=frozenset()):
    return career_tree.build_more_nodes(
        SCORES, {}, hidden_ids, frozenset(), "\n".join(EVIDENCE), node_id, set(shown), set(field_ids))


class TestShowMore(unittest.TestCase):

    def test_area_layer_is_real_new_and_spread_across_fields(self):
        _, careers, fields = first_view()
        shown = [c["soc"] for c in careers]
        area_fields = [f["id"] for f in fields if f["parent"] == "p:A"]

        layer = more("p:A", shown, area_fields)
        added = [n for n in layer["nodes"] if n["type"] == "career"]

        self.assertEqual(len(added), career_tree.MORE_AREA_BATCH)
        self.assertGreater(layer["remaining"], 0)
        per_field = {}
        for node in added:
            self.assertIn(node["soc"], REAL_IDS)
            self.assertNotIn(node["soc"], shown)
            self.assertTrue(node["why"])
            per_field[minor_group(node["soc"])] = per_field.get(minor_group(node["soc"]), 0) + 1
        self.assertLessEqual(max(per_field.values()), career_tree.MORE_AREA_MAX_PER_FIELD)

    def test_every_added_node_has_a_parent_on_the_map_or_in_the_layer(self):
        _, careers, fields = first_view()
        area_fields = {f["id"] for f in fields if f["parent"] == "p:A"}
        layer = more("p:A", [c["soc"] for c in careers], area_fields)

        new_field_ids = {n["id"] for n in layer["nodes"] if n["type"] == "field"}
        self.assertFalse(new_field_ids & area_fields)
        for node in layer["nodes"]:
            if node["type"] == "field":
                self.assertEqual(node["parent"], "p:A")
                self.assertTrue(node["label"] and node["officialTitle"])
            else:
                self.assertIn(node["parent"], area_fields | new_field_ids)
        targets = {e["target"] for e in layer["edges"]}
        self.assertEqual(targets, {n["id"] for n in layer["nodes"]})

    def test_field_layer_stays_in_that_field(self):
        _, careers, fields = first_view()
        field = next(f for f in fields if f["id"].startswith("f:A-27-2"))
        layer = more(field["id"], [c["soc"] for c in careers], [])

        self.assertTrue(layer["nodes"])
        self.assertLessEqual(len(layer["nodes"]), career_tree.MORE_FIELD_BATCH)
        for node in layer["nodes"]:
            self.assertEqual(node["type"], "career")
            self.assertEqual(node["parent"], field["id"])
            self.assertTrue(node["soc"].startswith("27-2"))

    def test_layers_never_repeat_and_run_out(self):
        _, careers, fields = first_view()
        field = next(f for f in fields if f["id"].startswith("f:A-27-2"))
        shown = [c["soc"] for c in careers]
        for _ in range(20):
            layer = more(field["id"], shown, [])
            new = [n["soc"] for n in layer["nodes"]]
            self.assertFalse(set(new) & set(shown))
            shown += new
            if layer["remaining"] == 0:
                break
        self.assertEqual(layer["remaining"], 0)
        self.assertEqual(more(field["id"], shown, [])["nodes"], [])

    def test_hidden_occupations_are_never_offered(self):
        _, careers, fields = first_view()
        field = next(f for f in fields if f["id"].startswith("f:A-27-2"))
        shown = [c["soc"] for c in careers]
        offered = more(field["id"], shown, [])["nodes"][0]["soc"]
        again = more(field["id"], shown, [], hidden_ids=frozenset({offered}))
        self.assertNotIn(offered, [n["soc"] for n in again["nodes"]])

    def test_bad_or_unshown_nodes_give_nothing(self):
        for node_id in ["", "you", "o:27-2031.00", "p:Z", "f:A", "p:A-27-2", "p:E", "f:E-11-1"]:
            with self.subTest(node_id=node_id):
                self.assertEqual(more(node_id, [], [])["nodes"], [])


class TestDepthValidation(unittest.TestCase):

    def test_good_response_is_kept_and_trimmed(self):
        depth = validate_depth(json.loads(json.dumps(GOOD_DEPTH)), "Dancers")
        self.assertEqual([w["setting"] for w in depth["workplaces"]],
                         ["Dance companies and troupes", "Film and television", "Dance schools"])
        self.assertEqual(depth["workplaces"][0]["examples"], ["Nritarutya", "The Royal Ballet"])
        self.assertEqual([s["name"] for s in depth["specialisations"]], ["Ballet", "Hip-hop", "Kathak"])

    def test_malformed_entries_are_dropped_not_repaired(self):
        depth = validate_depth({
            "workplaces": [{"setting": "Hospitals"}, {"setting": ""}, "Clinics", {"setting": "Schools", "examples": [3]}],
            "specialisations": [
                {"name": "Ballet", "about": "A classical style."},
                {"name": "ballet", "about": "Duplicate."},
                {"name": "Dancers", "about": "The occupation itself."},
                {"name": "A very long made up job title here", "about": "Too many words."},
                {"name": "No about"},
                "Jazz",
            ],
        }, "Dancers")
        self.assertEqual(depth["workplaces"], [{"setting": "Hospitals", "examples": []},
                                               {"setting": "Schools", "examples": []}])
        self.assertEqual(depth["specialisations"], [{"name": "Ballet", "about": "A classical style."}])

    def test_unusable_response_is_rejected(self):
        for bad in [None, [], "text", {}, {"workplaces": [{"setting": "Only one"}], "specialisations": []}]:
            with self.subTest(bad=bad):
                self.assertIsNone(validate_depth(bad, "Dancers"))

    def test_depth_never_contains_occupations(self):
        depth = validate_depth(json.loads(json.dumps(GOOD_DEPTH)), "Dancers")
        self.assertEqual(set(depth), {"workplaces", "specialisations"})
        for spec in depth["specialisations"]:
            self.assertEqual(set(spec), {"name", "about"})


class TestDepthEndpoints(unittest.TestCase):

    SOC = ID_BY_TITLE["Dancers"]
    CACHE_KEY = f"depth:{SOC}"

    @classmethod
    def setUpClass(cls):
        db.init_db()
        cls.client = TestClient(main.app)

        email = f"test-depth-{os.urandom(4).hex()}@example.com"
        r = cls.client.post("/api/auth/signup", json={"email": email, "password": "testpass123"})
        assert r.status_code == 200, r.text
        cls.token = r.json()["token"]
        cls.session_id = cls.client.post("/api/chat/start", json={"token": cls.token}).json()["session_id"]

        for line in EVIDENCE:
            db.add_message(cls.session_id, "user", line)
        db.log_event(cls.session_id, "score_computed", {"scores": SCORES, "scored_at_message_count": 7})

        # The depth cache is shared by every user - put back whatever
        # a real run had stored once this test is done with the key.
        cls.saved_depth = db.get_cached_string(cls.CACHE_KEY)
        cls._clear_depth_cache()

    @classmethod
    def _clear_depth_cache(cls):
        conn = db.get_db()
        conn.execute("DELETE FROM generated_strings WHERE cache_key = ?", (cls.CACHE_KEY,))
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        cls._clear_depth_cache()
        if cls.saved_depth is not None:
            db.set_cached_string(cls.CACHE_KEY, "career_depth", cls.saved_depth)
        conn = db.get_db()
        conn.execute("DELETE FROM messages WHERE session_id = ?", (cls.session_id,))
        conn.execute("DELETE FROM events WHERE session_id = ?", (cls.session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (cls.session_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (cls.token,))
        conn.commit()
        conn.close()

    def test_show_more_endpoint(self):
        _, careers, fields = first_view()
        body = {
            "session_id": self.session_id, "token": self.token, "node_id": "p:A",
            "shown": [c["soc"] for c in careers],
            "fields": [f["id"] for f in fields if f["parent"] == "p:A"],
        }
        r = self.client.post("/api/career-tree/more", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        added = [n for n in data["nodes"] if n["type"] == "career"]
        self.assertEqual(len(added), career_tree.MORE_AREA_BATCH)
        for node in added:
            self.assertIn(node["soc"], REAL_IDS)
            self.assertNotIn(node["soc"], body["shown"])

        r = self.client.post("/api/career-tree/more", json={**body, "token": "not-a-real-token"})
        self.assertEqual(r.status_code, 401)

    def test_depth_is_generated_once_then_served_from_cache(self):
        self._clear_depth_cache()
        calls = []

        def fake_generate(title, description, tasks):
            calls.append(title)
            return validate_depth(json.loads(json.dumps(GOOD_DEPTH)), title)

        url = f"/api/career-depth/{self.session_id}/{self.SOC}"
        with patch.object(main, "generate_career_depth", fake_generate):
            first = self.client.get(url, params={"token": self.token})
            second = self.client.get(url, params={"token": self.token})

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(calls, ["Dancers"])
        self.assertEqual(first.json()["specialisations"], second.json()["specialisations"])
        self.assertEqual(first.json()["workplaces"][0]["setting"], "Dance companies and troupes")

    def test_failed_generation_is_not_cached(self):
        self._clear_depth_cache()
        url = f"/api/career-depth/{self.session_id}/{self.SOC}"
        with patch.object(main, "generate_career_depth", lambda *args: None):
            r = self.client.get(url, params={"token": self.token})
        self.assertEqual(r.status_code, 503)
        self.assertIsNone(db.get_cached_string(self.CACHE_KEY))

    def test_depth_is_only_for_real_occupations(self):
        called = []
        with patch.object(main, "generate_career_depth", lambda *args: called.append(args)):
            r = self.client.get(f"/api/career-depth/{self.session_id}/99-9999.00", params={"token": self.token})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
