from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.import_kpredict_data import (
    build_id_map,
    check_pseudonym_continuity,
    import_rare_findings,
    make_pseudonym,
    parse_numeric_text,
    path_is_inside_repo,
    validate_release_name,
)


class KpredictImportTests(unittest.TestCase):
    def test_pseudonyms_are_stable_without_exposing_source_ids(self):
        key = b"test-key" * 4
        first = make_pseudonym("SOURCE-ONE", key)
        self.assertEqual(first, make_pseudonym("SOURCE-ONE", key))
        self.assertNotIn("SOURCE", first)
        self.assertRegex(first, r"^KP-[A-F0-9]{12}$")

    def test_id_map_rejects_duplicate_source_ids(self):
        with self.assertRaises(ValueError):
            build_id_map(["SOURCE-ONE", "SOURCE-ONE"], b"test-key" * 4)

    def test_release_name_cannot_escape_output_root(self):
        for value in ("", ".", "..", "../../escape", "release/name"):
            with self.assertRaises(ValueError):
                validate_release_name(value)
        self.assertEqual(validate_release_name("2026-09-17"), "2026-09-17")

    def test_repository_is_not_a_valid_private_output_root(self):
        self.assertTrue(path_is_inside_repo(Path(__file__).resolve().parents[1] / "private"))
        with tempfile.TemporaryDirectory() as temporary:
            self.assertFalse(path_is_inside_repo(Path(temporary)))

    def test_rare_import_stores_portal_disease_slug(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "rare.tsv"
            output = root / "release"
            output.mkdir()
            pd.DataFrame([
                {
                    "IID": "SOURCE-ONE",
                    "track": "panel",
                    "xprs_disease": "diabetes",
                    "xprs_disease_label": "Type 2 Diabetes",
                    "gene": "GENE1",
                    "variant": "1:100:A:G",
                    "moi_call": "alert",
                }
            ]).to_csv(source, sep="\t", index=False)
            mapping = pd.DataFrame([
                {"source_iid": "SOURCE-ONE", "pseudonym": "KP-ABCDEF123456"}
            ])

            import_rare_findings(source, mapping, b"test-key" * 4, output, hash_source=False)

            findings = pd.read_parquet(output / "rare_findings.parquet")
            self.assertEqual(findings.iloc[0]["xprs_disease"], "type2_diabetes")


    def test_numeric_text_parses_handoff_formats_strictly(self):
        values = pd.Series(["0.01%", "2.2e-03%", "0%", "—", "", "3.098e-06", "0.000e+00", None])
        parsed = parse_numeric_text(values, "gnomad_af_eas")

        self.assertAlmostEqual(parsed[0], 0.0001)
        self.assertAlmostEqual(parsed[1], 2.2e-05)
        self.assertEqual(parsed[2], 0.0)
        self.assertTrue(parsed[3:5].isna().all())
        self.assertAlmostEqual(parsed[5], 3.098e-06)
        self.assertEqual(parsed[6], 0.0)
        self.assertTrue(pd.isna(parsed[7]))
        with self.assertRaisesRegex(ValueError, "gnomad_af_eas: 1 value"):
            parse_numeric_text(pd.Series(["0.01%", "about 1%"]), "gnomad_af_eas")

    def test_rare_import_keeps_percent_frequencies(self):
        # Regression: the September release stored gnomad_af_eas as NaN for every row.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "rare.tsv"
            output = root / "release"
            output.mkdir()
            pd.DataFrame([{
                "IID": "SOURCE-ONE", "track": "other", "xprs_disease": "", "gene": "GENE1",
                "variant": "1:100:A:G", "moi_call": "carrier",
                "gnomad_af": "3.098e-06", "gnomad_af_eas": "0.01%", "cohort_af": "0.000109",
            }]).to_csv(source, sep="\t", index=False)
            mapping = pd.DataFrame([{"source_iid": "SOURCE-ONE", "pseudonym": "KP-ABCDEF123456"}])

            import_rare_findings(source, mapping, b"test-key" * 4, output, hash_source=False)

            row = pd.read_parquet(output / "rare_findings.parquet").iloc[0]
            self.assertAlmostEqual(row["gnomad_af_eas"], 0.0001)
            self.assertAlmostEqual(row["gnomad_af"], 3.098e-06)

    def test_pseudonym_continuity_is_enforced(self):
        key = b"k" * 32
        previous = build_id_map(["A", "B"], key)

        check_pseudonym_continuity(build_id_map(["A", "B"], key), previous)  # same key: passes
        with self.assertRaisesRegex(ValueError, "Pseudonyms differ"):
            check_pseudonym_continuity(build_id_map(["A", "B"], b"x" * 32), previous)
        with self.assertRaisesRegex(ValueError, "1 new and 0 missing"):
            check_pseudonym_continuity(build_id_map(["A", "B", "C"], key), previous)


if __name__ == "__main__":
    unittest.main()
