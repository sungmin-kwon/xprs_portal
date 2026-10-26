from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from retrieval_coverage import build_retrieval_coverage


class RetrievalCoverageTests(unittest.TestCase):
    def test_coverage_is_observed_and_combines_provider_caches(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            s2 = root / "s2"
            epmc = root / "epmc"
            s2.mkdir()
            epmc.mkdir()
            (s2 / "TP53_general_s2.json").write_text(json.dumps({
                "gene": "TP53", "phenotype": None, "fetch_ok": True,
                "pagination_complete": True, "data": [{"paperId": "s2-one"}],
            }), encoding="utf-8")
            (epmc / "tp53_general_epmc.json").write_text(json.dumps({
                "gene": "TP53", "phenotype": None, "fetch_ok": True,
                "pagination_complete": True, "eligible_count": 1,
                "data": [{"publication_id": "PMID:123"}],
            }), encoding="utf-8")
            result = build_retrieval_coverage(
                inventory={
                    "document_count": 2, "gene_count": 1,
                    "genes": [{"gene": "TP53", "total": 2, "pools": {"general": 2}, "phenotypes": {}, "sources": {"semanticscholar": 1, "europe_pmc": 1}}],
                },
                cache_dirs={"semanticscholar": s2, "europe_pmc": epmc},
            )

        pool = result["genes"][0]["pools"][0]
        self.assertEqual(result["genes"][0]["gene"], "TP53")
        self.assertNotIn("scope", result["genes"][0])
        self.assertEqual({row["source"] for row in pool["sources"]}, {"semanticscholar", "europe_pmc"})
        self.assertEqual(result["summary"]["providers"], ["europe_pmc", "semanticscholar"])

    def test_empty_store_does_not_invent_a_frequency_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = build_retrieval_coverage(
                inventory={"document_count": 0, "gene_count": 0, "genes": []},
                cache_dirs={"semanticscholar": root / "s2", "europe_pmc": root / "epmc"},
            )
        self.assertEqual(result["genes"], [])
        self.assertEqual(result["summary"]["tracked_query_pools"], 0)


if __name__ == "__main__":
    unittest.main()
