"""
Career Graph selection: hybrid ranking (RIASEC fit + local topic
relevance). Fully deterministic - no AI call, no network, no
database. Run from the repo root.

The scores below are what the real scorer returned for each
conversation; they're fixed here so the test doesn't depend on it.
"""

import json
import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "Scripts"))
sys.path.insert(0, os.path.join(ROOT_DIR, "ai_core"))

import career_tree
import topic_relevance
import tree_enrichment

with open(os.path.join(ROOT_DIR, "Outputs", "career_graph.json"), encoding="utf-8") as f:
    OCCUPATIONS = json.load(f)
ID_BY_TITLE = {occ["title"]: occ["id"] for occ in OCCUPATIONS}

SCENARIOS = {
    "dancing": {
        "scores": {"builds_tinkers": 0.1, "investigates_why": 0.2, "creates_expresses": 0.85,
                   "works_with_people": 0.1, "organizes_systems": 0.4, "leads_persuades": 0.05},
        "evidence": "\n".join([
            "dancing. i've been learning contemporary from youtube videos in my room",
            "the movement i think, how you can show a feeling with just your body",
            "alone mostly. i like practising by myself until a move feels right",
            "i replay the same 8 counts again and again and watch myself in the mirror until the timing is right",
            "my flexibility and turns, and remembering long routines",
            "sometimes i mix moves from different videos into my own little routine",
            "maybe hip hop, it looks fun but harder",
        ]),
        "expect": ["Dancers", "Choreographers"],
    },
    "journalism": {
        "scores": {"builds_tinkers": 0.1, "investigates_why": 0.85, "creates_expresses": 0.8,
                   "works_with_people": 0.7, "organizes_systems": 0.4, "leads_persuades": 0.3},
        "evidence": "\n".join([
            "i like reading news and i started writing small reports about things happening in my school",
            "finding out what really happened. people say different things and i like checking who is right",
            "i interview people alone but i like talking to lots of people for a story",
            "when i get a good quote from a teacher or student and write the article that same evening",
            "asking better questions in interviews and writing headlines",
            "i wrote an article about the canteen price hike for our school newspaper",
            "maybe start a small news page online about our town",
        ]),
        "expect": ["News Analysts, Reporters, and Journalists"],
    },
    "guitar": {
        "scores": {"builds_tinkers": 0.2, "investigates_why": 0.1, "creates_expresses": 0.85,
                   "works_with_people": 0.5, "organizes_systems": 0.3, "leads_persuades": 0.1},
        "evidence": "\n".join([
            "playing guitar. i got an acoustic guitar last year and i practise chords every day",
            "the sound when a chord finally rings clean, and learning songs i like",
            "alone at home, but i want to play with a band someday",
            "learning a new song from tabs and playing along with the recording",
            "fingerpicking and switching chords faster. also i want to learn keyboard and drums",
            "i tried to make a small tune of my own on the guitar",
            "play at the school function with my friends",
        ]),
        "expect": ["Musicians and Singers"],
    },
    "composing": {
        "scores": {"builds_tinkers": 0.25, "investigates_why": 0.75, "creates_expresses": 0.9,
                   "works_with_people": 0.3, "organizes_systems": 0.55, "leads_persuades": 0.1},
        "evidence": "\n".join([
            "making my own music. i compose little melodies on a keyboard app and write them down",
            "how a few notes can change the whole mood. i like arranging which instrument plays what",
            "alone, i need quiet to compose",
            "i start with a melody, add harmony under it, then try to write a second part",
            "music theory, like chord progressions and how to write for different instruments",
            "i composed a two minute piece for piano and violin for my cousin's wedding video",
            "write a background score for a short film my friend is making",
        ]),
        "expect": ["Music Directors and Composers"],
    },
    "sound work": {
        "scores": {"builds_tinkers": 0.8, "investigates_why": 0.7, "creates_expresses": 0.8,
                   "works_with_people": 0.7, "organizes_systems": 0.5, "leads_persuades": 0.2},
        "evidence": "\n".join([
            "recording and mixing sound. i record my friends' songs on my phone and clean them up in audacity",
            "making it sound clear. removing noise, balancing the voice and the instruments, adding a bit of echo",
            "with others, they perform and i handle the mic and the laptop",
            "setting up the microphone properly, recording a few takes and then mixing them at night",
            "using an equalizer properly and understanding how speakers and mixers work",
            "i did the sound for our school annual day, the mics and the speakers",
            "learn proper audio editing software and maybe record a podcast",
        ]),
        "expect": ["Sound Engineering Technicians", "Audio and Video Technicians"],
    },
    "maths": {
        "scores": {"builds_tinkers": 0.55, "investigates_why": 0.85, "creates_expresses": 0.2,
                   "works_with_people": 0.35, "organizes_systems": 0.45, "leads_persuades": 0.1},
        "evidence": "\n".join([
            "maths. i like solving hard problems, especially number puzzles and geometry proofs",
            "that feeling when a proof finally works and everything fits logically",
            "alone first, then i like comparing methods with a friend",
            "picking one olympiad problem and trying different approaches for an hour",
            "probability and statistics, i find them tricky but interesting",
            "i wrote a small python program to check a pattern in prime numbers",
            "learn calculus early and try more olympiad papers",
        ]),
        "expect": ["Mathematicians", "Statisticians"],
    },
    "singing": {
        "scores": {"builds_tinkers": 0.1, "investigates_why": 0.3, "creates_expresses": 0.9,
                   "works_with_people": 0.5, "organizes_systems": 0.3, "leads_persuades": 0.1},
        "evidence": "\n".join([
            "singing. i sing all the time, mostly film songs and some carnatic i learnt as a kid",
            "controlling my voice, hitting a high note cleanly feels amazing",
            "alone for practice but i love singing on stage in front of people",
            "warming up my voice, then practising one song until the pitch is right",
            "breath control and singing in different styles",
            "i recorded a cover song and posted it online",
            "join the school choir and try a singing competition",
        ]),
        "expect": ["Musicians and Singers"],
    },
    "F1": {
        "scores": {"builds_tinkers": 0.85, "investigates_why": 0.8, "creates_expresses": 0.4,
                   "works_with_people": 0.05, "organizes_systems": 0.3, "leads_persuades": 0.05},
        "evidence": "\n".join([
            "formula 1. i watch every race and i'm obsessed with how the cars are designed",
            "the engineering, like aerodynamics, how the wings and floor make downforce, and the engines",
            "alone mostly, i read technical articles and watch car design breakdowns",
            "after a race i look at why one car was faster, tyre strategy and the pit stops",
            "understanding the physics of aerodynamics and how race engineers use data",
            "i built a small model car and tested different wing shapes with a fan",
            "learn some CAD and design my own car part",
        ]),
        "expect": ["Automotive Engineers", "Mechanical Engineers"],
    },
}

NO_TOPIC_TEXTS = [
    "idk\nnothing much\nok\nmaybe\ni just chill",
    "i like hanging out with my friends and watching youtube and sleeping. school is boring. "
    "i don't know what i like honestly, i just scroll my phone",
    "idk\nnothing much\nok\nmaybe\ni just chill\ni like hanging out with my friends\nschool is boring",
]

# The way a student who isn't sure what to say actually answers.
VAGUE_DANCING = "dancing\nit just makes me happy\nalone i guess\nidk\nhip hop maybe\nno\nnot sure"


def build(scenario, evidence=None, hidden_ids=frozenset()):
    return career_tree.build_career_tree_core(
        scenario["scores"], {}, hidden_ids, frozenset(), [],
        scenario["evidence"] if evidence is None else evidence,
    )


def career_titles(tree):
    return [n["fullTitle"] for n in tree["nodes"] if n["type"] == "career"]


class TestFirstView(unittest.TestCase):

    def test_obvious_careers_reach_the_first_view(self):
        for name, scenario in SCENARIOS.items():
            titles = career_titles(build(scenario))
            for expected in scenario["expect"]:
                with self.subTest(scenario=name, career=expected):
                    self.assertIn(expected, titles)

    def test_literal_match_is_flagged_as_a_topic_match(self):
        tree = build(SCENARIOS["dancing"])
        flagged = {n["fullTitle"] for n in tree["nodes"] if n.get("topicMatch")}
        self.assertIn("Dancers", flagged)
        self.assertLessEqual(len(flagged), topic_relevance.MAX_GUARANTEED_MATCHES)

    def test_text_with_no_topic_changes_nothing(self):
        scenario = SCENARIOS["dancing"]
        riasec_only = build(scenario, evidence="")
        for text in NO_TOPIC_TEXTS:
            with self.subTest(text=text[:20]):
                self.assertEqual(topic_relevance.topic_relevance(text), ({}, []))
                self.assertEqual(build(scenario, evidence=text), riasec_only)

    def test_one_clear_word_in_a_vague_conversation_is_enough(self):
        titles = career_titles(build(SCENARIOS["dancing"], evidence=VAGUE_DANCING))
        self.assertIn("Dancers", titles)
        self.assertIn("Choreographers", titles)

    def test_passing_remarks_never_become_guaranteed_matches(self):
        for text in ["ok cool. what styles are there?", "school is boring", "we play every evening",
                     "when i get a good quote from a teacher or student and write the article that same evening"]:
            with self.subTest(text=text[:20]):
                self.assertEqual(topic_relevance.topic_relevance(text)[1], [])

    def test_hidden_occupation_stays_hidden_even_as_a_strong_match(self):
        dancers = ID_BY_TITLE["Dancers"]
        tree = build(SCENARIOS["dancing"], hidden_ids=frozenset({dancers}))
        self.assertNotIn(dancers, [n["soc"] for n in tree["nodes"] if n["type"] == "career"])

    def test_each_thread_keeps_its_own_matches(self):
        scores = {"builds_tinkers": 0.3, "investigates_why": 0.7, "creates_expresses": 0.8,
                  "works_with_people": 0.2, "organizes_systems": 0.4, "leads_persuades": 0.1}
        evidence = [SCENARIOS["dancing"]["evidence"], SCENARIOS["maths"]["evidence"]]
        tree = career_tree.build_career_tree_core(scores, {}, frozenset(), frozenset(), [], evidence)
        titles = career_titles(tree)
        self.assertIn("Dancers", titles)
        self.assertIn("Mathematicians", titles)

    def test_diversity_rules_still_hold(self):
        for name, scenario in SCENARIOS.items():
            tree = build(scenario)
            careers = [n for n in tree["nodes"] if n["type"] == "career"]
            fields = [n for n in tree["nodes"] if n["type"] == "field"]
            with self.subTest(scenario=name):
                self.assertLessEqual(len(careers), career_tree.MAX_LEAVES)
                for field in fields:
                    members = [c for c in careers if c["parent"] == field["id"]]
                    self.assertLessEqual(len(members), career_tree.MAX_PER_FIELD, field["label"])
                self.assertEqual(len({c["soc"] for c in careers}), len(careers))
                for c in careers:
                    self.assertIn(c["soc"], ID_BY_TITLE.values())

    def test_more_occupations_continues_without_repeats(self):
        scenario = SCENARIOS["dancing"]
        shown = career_tree.determine_shown_patterns(scenario["scores"], {})
        high_points = career_tree.load_interest_high_points()
        _, first_view = career_tree.select_occupations(
            scenario["scores"], shown, high_points, evidence_text=scenario["evidence"])
        already = {occ["id"] for occ in first_view}

        batch, remaining = career_tree.more_occupations(
            scenario["scores"], shown, high_points, frozenset(), frozenset(), scenario["evidence"],
            pattern="creates_expresses", already_selected_ids=already)
        self.assertEqual(len(batch), career_tree.SHOW_MORE_BATCH)
        self.assertGreater(remaining, 0)
        self.assertFalse(already & {occ["id"] for occ in batch})


class TestFieldNodes(unittest.TestCase):

    def test_sibling_fields_never_share_a_label(self):
        for name, scenario in SCENARIOS.items():
            tree = build(scenario)
            for area in [n for n in tree["nodes"] if n["type"] == "area"]:
                sibling_labels = [n["label"] for n in tree["nodes"] if n.get("parent") == area["id"]]
                with self.subTest(scenario=name, area=area["label"]):
                    self.assertEqual(len(set(sibling_labels)), len(sibling_labels), sibling_labels)

    def test_official_title_is_kept_alongside(self):
        tree = build(SCENARIOS["dancing"])
        for field in [n for n in tree["nodes"] if n["type"] == "field"]:
            self.assertTrue(field["officialTitle"])


class TestPruneKeepsTopicMatches(unittest.TestCase):

    def test_topic_match_survives_a_failed_why_call(self):
        tree = {
            "nodes": [
                {"id": "you", "type": "hub", "label": "You"},
                {"id": "p:A", "type": "area", "label": "Create & express", "parent": "you"},
                {"id": "f:A-27-2", "type": "field", "label": "Dance", "parent": "p:A"},
                {"id": "o:1", "type": "career", "label": "Dancers", "parent": "f:A-27-2",
                 "relevant": False, "topicMatch": True, "why": "fallback"},
                {"id": "o:2", "type": "career", "label": "Actors", "parent": "f:A-27-2",
                 "relevant": False, "why": "fallback"},
            ],
            "edges": [
                {"source": "you", "target": "p:A", "kind": "branch"},
                {"source": "p:A", "target": "f:A-27-2", "kind": "branch"},
                {"source": "f:A-27-2", "target": "o:1", "kind": "branch"},
                {"source": "f:A-27-2", "target": "o:2", "kind": "branch"},
            ],
        }
        pruned = tree_enrichment._prune_irrelevant_careers(tree)
        kept = {n["id"]: n for n in pruned["nodes"]}
        self.assertIn("o:1", kept)
        self.assertNotIn("o:2", kept)
        self.assertEqual(kept["o:1"]["why"], tree_enrichment.TOPIC_MATCH_WHY)
        self.assertNotIn("topicMatch", kept["o:1"])


if __name__ == "__main__":
    unittest.main()
