from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

import pandas as pd

from disease_registry import get_disease_config
from plot_data import PlotDataStore


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "data" / "demo"
DEMO_IID = "DEMO_HG00436"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DemoDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((DEMO_DIR / "manifest.json").read_text(encoding="utf-8"))
        cls.gene_importance = pd.read_csv(DEMO_DIR / "all_individuals_gene_importance.csv")
        cls.annotated_info = pd.read_parquet(DEMO_DIR / "plot_cache" / "annotated_info.parquet")
        cls.prs_info = pd.read_parquet(DEMO_DIR / "plot_cache" / "prs_info.parquet")
        cls.full_prs = pd.read_parquet(DEMO_DIR / "plot_cache" / "full_prs.parquet")

    def test_only_the_demo_iid_has_detailed_contributions(self):
        self.assertEqual(list(self.gene_importance.columns), ["Gene", DEMO_IID])
        self.assertEqual(list(self.prs_info.columns), [DEMO_IID])
        self.assertEqual(len(self.gene_importance), 6500)
        self.assertEqual(len(self.prs_info), len(self.annotated_info))

    def test_background_distribution_is_relabelled(self):
        iids = list(self.full_prs["IID"].astype(str))
        self.assertEqual(iids.count(DEMO_IID), 1)
        background = [iid for iid in iids if iid != DEMO_IID]
        self.assertEqual(len(background), 502)
        self.assertEqual(len(set(background)), 502)
        self.assertTrue(all(re.fullmatch(r"BACKGROUND_\d{4}", iid) for iid in background))

    def test_manifest_checksums_match_tracked_files(self):
        self.assertEqual(self.manifest["demo_iid"], DEMO_IID)
        self.assertEqual(self.manifest["source_iid"], "HG00436")
        for details in self.manifest["files"].values():
            path = DEMO_DIR / details["path"]
            self.assertEqual(path.stat().st_size, details["bytes"])
            self.assertEqual(sha256_file(path), details["sha256"])

    def test_demo_supports_both_dashboard_plots(self):
        store = PlotDataStore(
            annotated_info=self.annotated_info,
            prs_info=self.prs_info,
            full_prs=self.full_prs,
            disease_config=get_disease_config("breast_cancer"),
        )
        payload = store.build_plot_payload(DEMO_IID)
        self.assertTrue(payload["manhattan"]["points"])
        self.assertEqual(payload["density"]["prs_value"], self.full_prs.loc[
            self.full_prs["IID"] == DEMO_IID,
            "PRS",
        ].iloc[0])
        self.assertEqual(len(payload["density"]["cohort_prs"]), 503)


if __name__ == "__main__":
    unittest.main()
