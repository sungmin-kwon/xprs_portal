from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.literature_enrichment import (
    S2_ENRICHMENT_API_KEY_MIN_INTERVAL_SECONDS,
    EnrichmentJob,
    LiteratureEnrichmentQueue,
)
from agents.semantic_scholar import SemanticScholarAgent


def paper(number: int, *, eligible: bool = True) -> dict:
    return {
        "paperId": f"paper-{number}",
        "title": f"GENE1 paper {number}",
        "abstract": f"GENE1 evidence {number}" if eligible else None,
        "citationCount": 1,
        "entity_extraction_complete": True,
    }


class FakeRAG:
    def __init__(self):
        self.upserted = []

    def upsert_docs(self, docs):
        self.upserted.extend(docs)


class SemanticScholarPaginationTests(unittest.TestCase):
    def make_agent(self, root: Path) -> SemanticScholarAgent:
        agent = SemanticScholarAgent(api_key="test", cache_dir=root)
        cache_path = agent.cache_path_for_gene("GENE1")
        agent._write_cache_payload(
            cache_path,
            {
                "gene": "GENE1",
                "phenotype": None,
                "query": "GENE1",
                "fetch_ok": True,
                "result_count": 10,
                "page_size": 10,
                "raw_examined": 10,
                "next_offset": 10,
                "pagination_complete": False,
                "data": [paper(index) for index in range(10)],
            },
        )
        return agent

    def test_successful_cache_is_terminal_and_never_fetches_another_page(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make_agent(Path(directory))
            with patch.object(agent, "search") as search:
                result = agent.fetch_next_cached_page(
                    "GENE1", page_size=10, max_raw_results=50
                )

            self.assertTrue(result["ok"])
            self.assertEqual(result["reason"], "complete")
            self.assertTrue(result["pagination_complete"])
            search.assert_not_called()
            status = agent.pagination_status("GENE1")
            self.assertTrue(status["pagination_complete"])
            self.assertEqual(status["search_strategy_count"], 1)
            self.assertEqual(status["search_strategies_complete"], 1)
            self.assertIsNone(status["active_search_strategy"])

    def test_initial_fallback_clamps_an_oversized_limit_to_ten(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = SemanticScholarAgent(api_key="test", cache_dir=Path(directory))
            with patch.object(agent, "search", return_value=[paper(index) for index in range(10)]) as search:
                papers = agent.cached_for_gene("GENE1", limit=100, max_retries=1)

            self.assertEqual(len(papers), 10)
            self.assertEqual(search.call_args.kwargs["limit"], 10)
            status = agent.pagination_status("GENE1")
            self.assertTrue(status["pagination_complete"])
            self.assertEqual(status["paper_count"], 10)
            self.assertEqual(status["search_strategy_count"], 1)

    def test_background_worker_can_create_the_initial_fallback_cache(self):
        class InitialFallbackS2:
            def __init__(self):
                self.fetch_ok = False
                self.calls = []
                self.records = []
            def cached_papers(self, _gene, _phenotype=None):
                return [paper(1)] if self.fetch_ok else []
            def papers_to_docs(self, gene, papers, pool_type, phenotype=None):
                return [{
                    "id": item["paperId"],
                    "text": item["abstract"],
                    "meta": {
                        "gene": gene,
                        "pool_type": pool_type,
                        "phenotype": phenotype,
                    },
                } for item in papers]
            def pagination_status(self, *_args, **_kwargs):
                return {
                    "fetch_ok": self.fetch_ok,
                    "pagination_complete": False,
                    "zero_yield_pages": 0,
                }
            def cached_for_gene(self, gene, **kwargs):
                self.calls.append((gene, kwargs))
                self.fetch_ok = True
                return [paper(1)]
            def record_enrichment_status(self, *args, **kwargs):
                self.records.append((args, kwargs))

        s2 = InitialFallbackS2()
        rag = FakeRAG()
        enricher = LiteratureEnrichmentQueue.__new__(LiteratureEnrichmentQueue)
        enricher.s2 = s2
        enricher.rag = rag
        enricher._activity = threading.Condition()
        enricher._interactive_retrievals = 0
        job = EnrichmentJob(
            gene="GENE1",
            pool_type="general",
            phenotype=None,
            target_eligible=30,
            ready_at=0,
        )

        enricher._enrich(job)

        self.assertEqual(len(s2.calls), 1)
        self.assertEqual(s2.calls[0][1]["max_retries"], 1)
        self.assertEqual(
            s2.calls[0][1]["api_key_min_interval_seconds"],
            S2_ENRICHMENT_API_KEY_MIN_INTERVAL_SECONDS,
        )
        self.assertEqual([doc["id"] for doc in rag.upserted], ["paper-1"])

    def test_queue_status_lists_the_active_request_before_the_backlog(self):
        enricher = LiteratureEnrichmentQueue.__new__(LiteratureEnrichmentQueue)
        now = time.monotonic()
        active = EnrichmentJob(
            gene="HCG27",
            pool_type="phenotype",
            phenotype="breast cancer",
            target_eligible=20,
            ready_at=now,
        )
        queued = EnrichmentJob(
            gene="HLA-DRB1",
            pool_type="general",
            phenotype=None,
            target_eligible=30,
            ready_at=now + 30,
        )
        enricher._pending = {active.key, queued.key}
        enricher._job_details = {active.key: active, queued.key: queued}
        enricher._current_job_key = active.key
        enricher._current_job_state = "running"
        enricher._pending_lock = threading.Lock()
        enricher._activity = threading.Condition()
        enricher._interactive_retrievals = 0
        enricher._worker = type("Worker", (), {"is_alive": lambda self: True})()

        status = enricher.get_status()

        self.assertEqual(status["pending_jobs"], 2)
        self.assertEqual(status["queued_jobs"], 1)
        self.assertEqual(status["jobs"][0]["query"], "HCG27 breast cancer")
        self.assertEqual(status["jobs"][0]["state"], "running")
        self.assertEqual(status["jobs"][1]["query"], "HLA-DRB1")
        self.assertEqual(status["jobs"][1]["state"], "queued")


if __name__ == "__main__":
    unittest.main()
