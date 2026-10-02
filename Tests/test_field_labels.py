"""
Student-friendly field labels for SOC groups (backend/soc_titles.py)
and the rule that sibling fields never share one
(career_tree.field_labels). No AI call, no network, no database.
Run from the repo root.
"""

import json
import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "Scripts"))

import career_tree
from soc_titles import (
    field_display_label, minor_title,
    FIELD_DISPLAY_MAJOR_LABELS, FIELD_DISPLAY_MINOR_LABELS, FIELD_DISPLAY_BROAD_LABELS,
    MAJOR_GROUP_TITLES, MINOR_GROUP_TITLES,
)

with open(os.path.join(ROOT_DIR, "Outputs", "career_graph.json"), encoding="utf-8") as f:
    OCCUPATIONS = json.load(f)
ID_BY_TITLE = {occ["title"]: occ["id"] for occ in OCCUPATIONS}


class TestFieldLabels(unittest.TestCase):

    def test_minor_and_major_group_labels(self):
        self.assertEqual(field_display_label("27-2"), "Performing Arts")
        self.assertEqual(field_display_label("27"), "Arts, Media & Entertainment")

    def test_every_group_in_the_dataset_has_a_label(self):
        for occ in OCCUPATIONS:
            self.assertIn(occ["id"][:2], FIELD_DISPLAY_MAJOR_LABELS, occ["title"])
            self.assertIn(occ["id"][:4], FIELD_DISPLAY_MINOR_LABELS, occ["title"])

    def test_labels_only_exist_for_real_groups(self):
        self.assertLessEqual(set(FIELD_DISPLAY_MAJOR_LABELS), set(MAJOR_GROUP_TITLES))
        self.assertLessEqual(set(FIELD_DISPLAY_MINOR_LABELS), set(MINOR_GROUP_TITLES))
        real_broad_groups = {occ["id"][:6] for occ in OCCUPATIONS}
        self.assertLessEqual(set(FIELD_DISPLAY_BROAD_LABELS), real_broad_groups)

    def test_members_in_one_broad_group_get_its_label(self):
        ids = [ID_BY_TITLE["Dancers"], ID_BY_TITLE["Choreographers"]]
        self.assertEqual(field_display_label("27-2", ids), "Dance")
        self.assertEqual(field_display_label("27-203"), "Dance")
        mixed = [ID_BY_TITLE["Dancers"], ID_BY_TITLE["Musicians and Singers"]]
        self.assertEqual(field_display_label("27-2", mixed), "Performing Arts")

    def test_sports_are_not_called_performing_arts(self):
        ids = [ID_BY_TITLE["Dancers"], ID_BY_TITLE["Coaches and Scouts"]]
        self.assertEqual(field_display_label("27-2", ids), "Performing Arts & Sports")

    def test_unknown_code_falls_back_to_the_official_title(self):
        self.assertEqual(field_display_label("99-9"), minor_title("99-9"))

    def test_sibling_fields_never_share_a_label(self):
        by_minor = {}
        for occ in OCCUPATIONS:
            by_minor.setdefault(occ["id"][:4], []).append(occ)
        split_groups = 0
        for minor, occs in by_minor.items():
            fields = career_tree.group_into_fields(occs)
            if len(fields) < 2:
                continue
            split_groups += 1
            labels = career_tree.field_labels(fields)
            with self.subTest(minor=minor):
                self.assertEqual(len(set(labels.values())), len(labels), labels)
        self.assertGreater(split_groups, 10)


if __name__ == "__main__":
    unittest.main()
