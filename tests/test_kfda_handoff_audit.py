from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.audit_kfda_handoff import (
    EXPECTED_RARE_COLUMNS,
    summarize_rare_findings,
    write_private_manifest,
)


class KfdaHandoffAuditTests(unittest.TestCase):
    def test_private_manifest_refuses_repository_output(self):
        with self.assertRaises(ValueError):
            write_private_manifest(
                Path(__file__).resolve().parents[1] / "audit.json",
                {"contains_participant_ids": False},
            )

    def test_private_manifest_uses_private_file_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "audit.json"
            write_private_manifest(output, {"contains_participant_ids": False})
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_rare_summary_never_contains_participant_values(self):
        rows = []
        for iid, call, track in (("PRIVATE_A", "alert", "panel"), ("PRIVATE_B", "carrier", "other")):
            row = {column: "" for column in EXPECTED_RARE_COLUMNS}
            row.update({
                "IID": iid,
                "track": track,
                "xprs_disease": "breast_cancer",
                "gene": "GENE1",
                "variant": f"variant-{iid}",
                "moi_call": call,
                "qc_pass": "True",
            })
            rows.append(row)

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "rare.tsv"
            pd.DataFrame(rows, columns=EXPECTED_RARE_COLUMNS).to_csv(path, sep="\t", index=False)
            summary, _ = summarize_rare_findings(path)

        serialized = repr(summary)
        self.assertNotIn("PRIVATE_A", serialized)
        self.assertNotIn("PRIVATE_B", serialized)
        self.assertEqual(summary["finding_iids"], 2)


if __name__ == "__main__":
    unittest.main()
