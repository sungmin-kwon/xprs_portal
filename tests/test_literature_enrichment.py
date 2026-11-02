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

    def test_next_page_is_appended_deduplicated_and_checkpointed(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make_agent(Path(directory))
            page = [paper(9)] + [paper(index) for index in range(10, 19)]
            with patch.object(agent, "search", return_value=page) as search:
                result = agent.fetch_next_cached_page(
                    "GENE1", page_size=10, max_raw_results=50
                )

            self.assertTrue(result["ok"])
            self.assertEqual(result["raw_examined"], 20)
            self.assertEqual(len(result["all_papers"]), 19)
            self.assertFalse(result["pagination_complete"])
            self.assertEqual(search.call_args.kwargs["offset"], 10)
            self.assertEqual(search.call_args.kwargs["limit"], 10)
            status = agent.pagination_status("GENE1")
            self.assertEqual(status["next_offset"], 20)
            self.assertEqual(status["paper_count"], 19)

    def test_short_page_marks_relevance_search_exhausted(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make_agent(Path(directory))
            with patch.object(
                agent,
                "search",
                return_value=[paper(10), paper(11)],
            ):
                result = agent.fetch_next_cached_page(
                    "GENE1", page_size=10, max_raw_results=50
                )
            self.assertTrue(result["pagination_complete"])
            self.assertTrue(agent.pagination_status("GENE1")["pagination_complete"])

    def test_phenotype_alias_query_runs_after_canonical_query_is_exhausted(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = SemanticScholarAgent(api_key="test", cache_dir=Path(directory))
            cache_path = agent.cache_path_for_gene("CDKAL1", "type 2 diabetes")
            agent._write_cache_payload(cache_path, {
                "gene": "CDKAL1",
                "phenotype": "type 2 diabetes",
                "query": "CDKAL1 type 2 diabetes",
                "fetch_ok": True,
                "raw_examined": 4,
                "next_offset": 4,
                "pagination_complete": True,
                "data": [],
            })

            with patch.object(agent, "search", return_value=[{
                "paperId": "alias-hit",
                "title": "CDKAL1 and T2D",
                "abstract": "CDKAL1 contributes to T2D susceptibility.",
                "citationCount": 1,
            }]) as search:
                result = agent.fetch_next_cached_page(
                    "CDKAL1",
                    phenotype="type 2 diabetes",
                    page_size=10,
                    max_raw_results=50,
                )

            self.assertTrue(result["ok"])
            self.assertEqual(result["search_strategy"], "phenotype_alias_1")
            self.assertEqual(search.call_args.args[0], "CDKAL1 t2d")
            self.assertEqual(search.call_args.kwargs["offset"], 0)
            self.assertEqual(
                agent.pagination_status("CDKAL1", "type 2 diabetes")["active_search_strategy"],
                "phenotype_alias_2",
            )

    def test_low_yield_strategy_can_advance_without_discarding_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = SemanticScholarAgent(api_key="test", cache_dir=Path(directory))
            cache_path = agent.cache_path_for_gene("GML")
            agent._write_cache_payload(cache_path, {
                "gene": "GML",
                "phenotype": None,
                "query": "GML glycosylphosphatidylinositol anchored molecule like LY6DL",
                "fetch_ok": True,
                "raw_examined": 20,
                "next_offset": 20,
                "pagination_complete": False,
                "data": [{"paperId": "kept", "title": "GML evidence"}],
            })

            self.assertTrue(agent.advance_to_next_search_strategy("GML"))
            status = agent.pagination_status("GML")
            self.assertEqual(status["active_search_strategy"], "symbol_gene")
            self.assertEqual([p["paperId"] for p in agent.cached_papers("GML")], ["kept"])

    def test_background_worker_stops_at_eligible_target(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make_agent(Path(directory))
            rag = FakeRAG()
            enricher = LiteratureEnrichmentQueue.__new__(LiteratureEnrichmentQueue)
            enricher.s2 = agent
            enricher.rag = rag
            enricher._activity = __import__("threading").Condition()
            enricher._interactive_retrievals = 0
            job = EnrichmentJob(
                gene="GENE1",
                pool_type="general",
                phenotype=None,
                target_eligible=12,
                ready_at=0,
            )
            with patch.object(
                agent,
                "search",
                return_value=[paper(index) for index in range(10, 20)],
            ) as search:
                enricher._enrich(job)

            self.assertEqual(len(rag.upserted), 10)
            self.assertEqual(
                search.call_args.kwargs["api_key_min_interval_seconds"],
                S2_ENRICHMENT_API_KEY_MIN_INTERVAL_SECONDS,
            )
            status = agent.pagination_status("GENE1")
            self.assertTrue(status["enrichment_complete"])
            self.assertEqual(status["enrichment_stop_reason"], "eligible_target")
            self.assertEqual(status["eligible_count"], 20)

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

    def test_two_zero_yield_pages_are_a_persisted_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make_agent(Path(directory))
            rag = FakeRAG()
            enricher = LiteratureEnrichmentQueue.__new__(LiteratureEnrichmentQueue)
            enricher.s2 = agent
            enricher.rag = rag
            enricher._activity = __import__("threading").Condition()
            enricher._interactive_retrievals = 0
            job = EnrichmentJob(
                gene="GENE1",
                pool_type="general",
                phenotype=None,
                target_eligible=30,
                ready_at=0,
            )
            pages = [
                [paper(index, eligible=False) for index in range(10, 20)],
                [paper(index, eligible=False) for index in range(20, 30)],
            ]
            with (
                patch.object(agent, "search", side_effect=pages) as search,
                patch(
                    "agents.literature_enrichment.S2_ENRICHMENT_MAX_PAGES_PER_JOB",
                    2,
                ),
            ):
                enricher._enrich(job)

            self.assertEqual(search.call_count, 2)
            self.assertEqual(rag.upserted, [])
            status = agent.pagination_status("GENE1")
            self.assertTrue(status["enrichment_complete"])
            self.assertEqual(status["enrichment_stop_reason"], "zero_yield_pages")
            self.assertEqual(status["zero_yield_pages"], 2)

    def test_admin_continuation_fetches_only_one_page_per_job(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make_agent(Path(directory))
            rag = FakeRAG()
            enricher = LiteratureEnrichmentQueue.__new__(LiteratureEnrichmentQueue)
            enricher.s2 = agent
            enricher.rag = rag
            enricher._activity = __import__("threading").Condition()
            enricher._interactive_retrievals = 0
            job = EnrichmentJob(
                gene="GENE1",
                pool_type="general",
                phenotype=None,
                target_eligible=30,
                ready_at=0,
            )
            pages = [
                [paper(index, eligible=False) for index in range(10, 20)],
                [paper(index, eligible=False) for index in range(20, 30)],
            ]
            with patch.object(agent, "search", side_effect=pages) as search:
                enricher._enrich(job)

            self.assertEqual(search.call_count, 1)
            status = agent.pagination_status("GENE1")
            self.assertFalse(status["enrichment_complete"])
            self.assertEqual(status["zero_yield_pages"], 1)

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
