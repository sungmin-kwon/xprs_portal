from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from kpredict_data import trait_overview


def write_release(root: Path, traits: list[tuple[str, str]]) -> None:
    """Minimal release: manifest plus traits/<slug>/individual_risk.parquet for two people."""
    entries = []
    for source_id, label in traits:
        slug = source_id.lower()
        folder = root / "traits" / slug
        folder.mkdir(parents=True)
        pd.DataFrame({
            "individual_id": ["person-1", "person-2"],
            "matrix_column": [0, 1],
            "sex": ["M", "F"],
            "raw_prs": [1.0, 2.0],
            "z": [1.8, float("nan")],
            "percentile": [96.4, float("nan")],
            "applicable": [True, False],
        }).to_parquet(folder / "individual_risk.parquet", index=False)
        entries.append({"source_trait_id": source_id, "portal_trait_slug": slug,
                        "trait_label": label, "reference_cohort": "test_cohort"})
    (root / "manifest.json").write_text(json.dumps({"diseases": [], "traits": entries}))


class TraitOverviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_traits_are_grouped_in_panel_order_with_unknown_ids_last(self):
        write_release(self.root, [("HbA1c", "Hemoglobin A1c"), ("LDLC", "LDL cholesterol"), ("NEWTRAIT", "New trait")])
        result = trait_overview(self.root, "person-1")

        self.assertEqual(result["trait_count"], 3)
        self.assertEqual([group["key"] for group in result["groups"]], ["lipids", "glucose", "other"])
        ldl = result["groups"][0]["traits"][0]
        self.assertEqual((ldl["slug"], ldl["label"]), ("ldlc", "LDL cholesterol"))
        self.assertTrue(math.isclose(ldl["percentile"], 96.4))
        self.assertTrue(math.isclose(ldl["z"], 1.8))

    def test_not_applicable_trait_has_no_values(self):
        write_release(self.root, [("LDLC", "LDL cholesterol")])
        row = trait_overview(self.root, "person-2")["groups"][0]["traits"][0]
        self.assertFalse(row["applicable"])
        self.assertIsNone(row["percentile"])
        self.assertIsNone(row["z"])

    def test_release_without_traits_returns_no_groups(self):
        (self.root / "manifest.json").write_text(json.dumps({"diseases": []}))
        self.assertEqual(trait_overview(self.root, "person-1")["groups"], [])

    def test_unknown_individual_is_rejected(self):
        write_release(self.root, [("LDLC", "LDL cholesterol")])
        with self.assertRaises(ValueError):
            trait_overview(self.root, "person-9")


if __name__ == "__main__":
    unittest.main()
