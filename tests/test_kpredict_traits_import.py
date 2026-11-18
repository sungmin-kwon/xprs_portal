from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.import_kpredict_traits import cross_check_risk, link_base_release, trait_slug


def tables():
    pseudonym_by_iid = pd.Series({"SRC-1": "pseudo-1", "SRC-2": "pseudo-2"})
    risk = pd.DataFrame({
        "individual_id": ["pseudo-1", "pseudo-2"],
        "sex": ["M", "F"],
        "raw_prs": [1.0, 2.0],
        "z": [-1.0, 1.0],
        "percentile": [10.0, 90.0],
    })
    prs = pd.DataFrame({"IID": ["SRC-2", "SRC-1"], "LDLC_PRS": [2.0, 1.0], "LDLC_z": [1.0, -1.0], "LDLC_pct": [90.0, 10.0]})
    sex = pd.DataFrame({"IID": ["SRC-1", "SRC-2"], "SEX": ["1", "2"]})
    return risk, prs, sex, pseudonym_by_iid


class TraitImportTests(unittest.TestCase):
    def test_trait_slugs_are_lowercase_identifiers(self):
        self.assertEqual(trait_slug("LDLC"), "ldlc")
        self.assertEqual(trait_slug("HbA1c"), "hba1c")
        with self.assertRaises(ValueError):
            trait_slug("1abc")

    def test_matching_tables_pass_cross_check(self):
        differences = cross_check_risk("LDLC", *tables())
        self.assertEqual(differences["raw_prs"], 0.0)

    def test_value_mismatch_is_rejected(self):
        risk, prs, sex, ids = tables()
        prs.loc[0, "LDLC_z"] = 1.5
        with self.assertRaisesRegex(ValueError, "z differs"):
            cross_check_risk("LDLC", risk, prs, sex, ids)

    def test_individual_outside_base_release_is_rejected(self):
        risk, prs, sex, ids = tables()
        prs.loc[0, "IID"] = "SRC-9"
        with self.assertRaisesRegex(ValueError, "outside the base release"):
            cross_check_risk("LDLC", risk, prs, sex, ids)

    def test_sex_mismatch_is_rejected(self):
        risk, prs, sex, ids = tables()
        sex.loc[0, "SEX"] = "2"
        with self.assertRaisesRegex(ValueError, "sex differs"):
            cross_check_risk("LDLC", risk, prs, sex, ids)

    def test_base_release_is_hard_linked_except_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / "base"
            (base / "diseases" / "x").mkdir(parents=True)
            (base / "diseases" / "x" / "contributions.f32").write_bytes(b"1234")
            (base / "manifest.json").write_text("{}")
            staging = Path(temporary) / "staging"
            staging.mkdir()

            self.assertEqual(link_base_release(base, staging), 1)
            linked = staging / "diseases" / "x" / "contributions.f32"
            self.assertTrue(os.path.samefile(linked, base / "diseases" / "x" / "contributions.f32"))
            self.assertFalse((staging / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
