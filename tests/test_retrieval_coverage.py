from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from retrieval_coverage import build_retrieval_coverage


def eligible_paper(paper_id: str, gene: str = "TP53", *, pmid: str | None = None):
    paper = {
        "paperId": paper_id,
        "title": f"{gene} evidence",
        "abstract": f"{gene} is associated with disease.",
        "citationCount": 1,
        "gene_identity_policy_version": 2,
        "gene_identity_validated": True,
        "extracted_genes": [gene],
    }
    if pmid:
        paper["pmid"] = pmid
    return paper


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

    def test_sparse_finished_epmc_does_not_hide_incomplete_semantic_scholar(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            s2 = root / "s2"; s2.mkdir()
            epmc = root / "epmc"; epmc.mkdir()
            (epmc / "tp53_general_epmc.json").write_text(json.dumps({
                "gene": "TP53", "phenotype": None, "fetch_ok": True,
                "pagination_complete": True,
                "data": [{**eligible_paper("PMID:1"), "publication_id": "PMID:1"}],
            }), encoding="utf-8")
            (s2 / "TP53_general_s2.json").write_text(json.dumps({
                "gene": "TP53", "phenotype": None, "query": "TP53",
                "fetch_ok": True, "pagination_complete": False,
                "search_strategy_version": 2,
                "search_strategies": [{
                    "name": "identity", "query": "TP53", "complete": False,
                    "raw_examined": 10,
                }],
                "data": [],
            }), encoding="utf-8")
            result = build_retrieval_coverage(
                inventory={
                    "document_count": 1, "gene_count": 1,
                    "genes": [{"gene": "TP53", "total": 1, "pools": {"general": 1}, "phenotypes": {}, "sources": {"europe_pmc": 1}}],
                },
                cache_dirs={"semanticscholar": s2, "europe_pmc": epmc},
            )

        pool = result["genes"][0]["pools"][0]
        self.assertEqual(pool["status"], "indexed")
        self.assertFalse(pool["target_reached"])
        self.assertFalse(pool["all_providers_terminal"])
        self.assertEqual(pool["incomplete_providers"], ["semanticscholar"])

    def test_incomplete_zero_yield_cache_is_not_labeled_ready_to_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            s2 = root / "s2"; s2.mkdir()
            epmc = root / "epmc"; epmc.mkdir()
            (s2 / "LAMC1-AS1_colorectal_cancer_s2.json").write_text(json.dumps({
                "gene": "LAMC1-AS1", "phenotype": "colorectal cancer",
                "query": "LAMC1-AS1 colorectal cancer", "fetch_ok": True,
                "pagination_complete": False, "search_strategy_version": 2,
                "search_strategies": [{
                    "name": "identity", "query": "LAMC1-AS1 colorectal cancer",
                    "complete": True, "raw_examined": 30,
                }],
                "data": [{"paperId": "unrelated", "title": "Unrelated paper"}],
            }), encoding="utf-8")
            result = build_retrieval_coverage(
                inventory={"document_count": 0, "gene_count": 0, "genes": []},
                cache_dirs={"semanticscholar": s2, "europe_pmc": epmc},
            )

        pool = result["genes"][0]["pools"][0]
        self.assertEqual(pool["status"], "partial")
        self.assertEqual(pool["eligible_count"], 0)
        statuses = {row["source"]: row for row in pool["provider_statuses"]}
        self.assertEqual(statuses["semanticscholar"]["state"], "incomplete")

    def test_target_reached_is_complete_without_fallback_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            s2 = root / "s2"; s2.mkdir()
            epmc = root / "epmc"; epmc.mkdir()
            papers = [
                {**eligible_paper(f"PMID:{index}"), "publication_id": f"PMID:{index}"}
                for index in range(5)
            ]
            (epmc / "tp53_general_epmc.json").write_text(json.dumps({
                "gene": "TP53", "phenotype": None, "fetch_ok": True,
                "pagination_complete": True, "data": papers,
            }), encoding="utf-8")
            result = build_retrieval_coverage(
                inventory={
                    "document_count": 5, "gene_count": 1,
                    "genes": [{"gene": "TP53", "total": 5, "pools": {"general": 5}, "phenotypes": {}, "sources": {"europe_pmc": 5}}],
                },
                cache_dirs={"semanticscholar": s2, "europe_pmc": epmc},
            )

        pool = result["genes"][0]["pools"][0]
        self.assertEqual(pool["status"], "complete")
        self.assertTrue(pool["target_reached"])
        self.assertEqual(pool["completion_reason"], "evidence_target")

    def test_eligible_count_is_deduplicated_across_providers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            s2 = root / "s2"; s2.mkdir()
            epmc = root / "epmc"; epmc.mkdir()
            epmc_paper = {
                **eligible_paper("PMID:123", pmid="123"),
                "publication_id": "PMID:123",
            }
            s2_paper = {
                **eligible_paper("s2-paper"),
                "externalIds": {"PubMed": "123"},
            }
            (epmc / "tp53_general_epmc.json").write_text(json.dumps({
                "gene": "TP53", "fetch_ok": True,
                "pagination_complete": True, "data": [epmc_paper],
            }), encoding="utf-8")
            (s2 / "TP53_general_s2.json").write_text(json.dumps({
                "gene": "TP53", "query": "TP53", "fetch_ok": True,
                "pagination_complete": True, "data": [s2_paper],
            }), encoding="utf-8")
            result = build_retrieval_coverage(
                inventory={"document_count": 1, "gene_count": 1, "genes": [{
                    "gene": "TP53", "total": 1, "pools": {"general": 1},
                    "phenotypes": {}, "sources": {"europe_pmc": 1},
                }]},
                cache_dirs={"semanticscholar": s2, "europe_pmc": epmc},
            )

        self.assertEqual(result["genes"][0]["pools"][0]["eligible_count"], 1)

    def test_empty_store_does_not_invent_a_frequency_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = build_retrieval_coverage(
                inventory={"document_count": 0, "gene_count": 0, "genes": []},
                cache_dirs={"semanticscholar": root / "s2", "europe_pmc": root / "epmc"},
            )
        self.assertEqual(result["genes"], [])
        self.assertEqual(result["summary"]["tracked_query_pools"], 0)

    def test_general_disease_evidence_is_shown_without_synthetic_query_pool(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = build_retrieval_coverage(
                inventory={
                    "document_count": 25,
                    "gene_count": 1,
                    "genes": [{
                        "gene": "CDKAL1",
                        "total": 25,
                        "pools": {"general": 25},
                        "phenotypes": {},
                        "general_phenotypes": {
                            "type 2 diabetes": 19,
                            "inflammatory bowel disease": 3,
                        },
                        "sources": {"europe_pmc": 25},
                    }],
                },
                cache_dirs={
                    "semanticscholar": root / "s2",
                    "europe_pmc": root / "epmc",
                },
            )

        gene = result["genes"][0]
        self.assertEqual(
            gene["covered_by_general"],
            [{"phenotype": "type 2 diabetes", "documents": 19}],
        )
        self.assertEqual(len(gene["pools"]), 1)
        self.assertIsNone(gene["pools"][0]["phenotype"])
        self.assertEqual(result["summary"]["tracked_query_pools"], 1)

    def test_provider_status_keeps_pool_specific_rate_limit_after_cached_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            s2 = root / "s2"; s2.mkdir()
            epmc = root / "epmc"; epmc.mkdir()
            (epmc / "tp53_general_epmc.json").write_text(json.dumps({
                "gene": "TP53", "fetch_ok": True,
                "pagination_complete": True,
                "data": [{**eligible_paper("PMID:1"), "publication_id": "PMID:1"}],
            }), encoding="utf-8")
            result = build_retrieval_coverage(
                inventory={"document_count": 1, "gene_count": 1, "genes": [{
                    "gene": "TP53", "total": 1, "pools": {"general": 1},
                    "phenotypes": {}, "sources": {"europe_pmc": 1},
                }]},
                cache_dirs={"semanticscholar": s2, "europe_pmc": epmc},
                provider_attempts=[{
                    "source": "semanticscholar", "gene": "TP53",
                    "phenotype": None, "outcome": "rate_limited",
                    "http_status": 429, "attempted_at": "2026-10-29T10:00:00+00:00",
                }],
            )

        statuses = {
            row["source"]: row
            for row in result["genes"][0]["pools"][0]["provider_statuses"]
        }
        self.assertEqual(statuses["europe_pmc"]["state"], "complete")
        self.assertEqual(statuses["semanticscholar"]["state"], "rate_limited")
        self.assertEqual(
            statuses["semanticscholar"]["last_attempt"]["http_status"],
            429,
        )


if __name__ == "__main__":
    unittest.main()
