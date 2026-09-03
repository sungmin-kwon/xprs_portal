from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import requests

from agents.rag import acquire_chroma_process_lock
from agents.semantic_scholar import SemanticScholarAgent, parse_retry_after_seconds
from reference_utils import ReferenceMetadataExtractor
from preindexing import (
    build_frequency_manifest,
    classify_gene_symbol,
    load_checkpoint,
    preindex_gene,
    save_checkpoint,
    select_frequent_genes,
    write_manifest,
)
from scripts.preindex_frequent_genes import (
    _cooldown_remaining_seconds,
    _normalize_open_breaker,
    _open_circuit_breaker,
    _record_api_successes,
)


class FakeS2:
    def __init__(self):
        self.cache_dir = Path("fake-cache")
        self.succeeded: set[tuple[str, str | None]] = set()
        self.calls: list[tuple[str, str | None, int]] = []

    def cached_query_succeeded(self, gene, phenotype=None):
        return (gene, phenotype) in self.succeeded

    def cached_for_gene(
        self,
        gene,
        limit,
        phenotype=None,
        progress_callback=None,
        request_timeout=15,
        max_retries=3,
    ):
        self.calls.append((gene, phenotype, limit))
        self.succeeded.add((gene, phenotype))
        return [{"paperId": f"{gene}-{phenotype or 'general'}"}]

    def papers_to_docs(self, gene, papers, pool_type, phenotype=None):
        return [{
            "id": f"{gene}-{pool_type}-{phenotype or 'general'}",
            "text": f"{gene} evidence",
            "meta": {
                "gene": gene,
                "pool_type": pool_type,
                "phenotype": phenotype,
            },
        }]


class FakeRAG:
    def __init__(self):
        self.docs: list[dict] = []

    @staticmethod
    def _matches(meta, where):
        clauses = where.get("$and", [where])
        return all(all(meta.get(key) == value for key, value in clause.items()) for clause in clauses)

    def has_documents(self, where):
        return any(self._matches(doc["meta"], where) for doc in self.docs)

    def upsert_docs(self, docs):
        self.docs.extend(docs)


class FailingS2:
    def __init__(self, status_code):
        self.cache_dir = Path("fake-cache")
        self.status_code = status_code
        self.calls = []

    def cached_query_succeeded(self, _gene, _phenotype=None):
        return False

    def cached_for_gene(
        self,
        gene,
        limit,
        phenotype=None,
        progress_callback=None,
        request_timeout=15,
        max_retries=3,
    ):
        self.calls.append((gene, phenotype, limit))
        return []

    def get_health_status(self):
        return {
            "last_status_code": self.status_code,
            "last_error": "simulated upstream failure",
        }


class FakeResponse:
    def __init__(self, status_code, data=None, text="error", headers=None):
        self.status_code = status_code
        self._data = data or {"data": []}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._data


class FrequencyManifestTests(unittest.TestCase):
    def test_top_and_bottom_occurrences_receive_equal_weight(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "importance.csv"
            source.write_text(
                "Gene,IID1,IID2\n"
                "GENEA,10,8\n"
                "GENEB,5,9\n"
                "GENEC,-5,-8\n"
                "GENED,-10,-9\n",
                encoding="utf-8",
            )
            rows, metadata = build_frequency_manifest(source, sweep_n=1)

        self.assertEqual(metadata["total_slots"], 4)
        self.assertEqual(rows[0]["gene"], "GENED")
        self.assertEqual(rows[0]["occurrences"], 2)
        self.assertEqual(rows[0]["risk_lowering_occurrences"], 2)
        self.assertEqual(rows[1]["gene"], "GENEA")
        self.assertEqual(rows[2]["gene"], "GENEB")

    def test_selection_excludes_placeholders_without_changing_rank_order(self):
        rows = [
            {"rank": 1, "gene": "NA_4", "occurrences": 9, "queryable": False},
            {"rank": 2, "gene": "TP53", "occurrences": 8, "queryable": True},
            {"rank": 3, "gene": "BRCA1", "occurrences": 7, "queryable": True},
        ]
        selected = select_frequent_genes(rows, max_genes=1)
        self.assertEqual([row["gene"] for row in selected], ["TP53"])
        self.assertEqual(classify_gene_symbol("NA_12"), (False, "placeholder"))
        self.assertEqual(classify_gene_symbol("HLA-DRB1"), (True, ""))

    def test_manifest_and_checkpoint_writes_are_reloadable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.csv"
            checkpoint = root / "state.json"
            rows = [{
                "rank": 1,
                "gene": "TP53",
                "occurrences": 2,
                "risk_increasing_occurrences": 1,
                "risk_lowering_occurrences": 1,
                "individual_coverage": 1.0,
                "slot_coverage": 1.0,
                "cumulative_slot_coverage": 1.0,
                "queryable": True,
                "exclusion_reason": "",
            }]
            write_manifest(manifest, rows)
            save_checkpoint(checkpoint, {"schema_version": 1, "genes": {"TP53": {"status": "completed"}}})
            loaded = load_checkpoint(checkpoint)

            self.assertIn("TP53", manifest.read_text(encoding="utf-8"))
            self.assertEqual(loaded["genes"]["TP53"]["status"], "completed")
            self.assertIn("updated_at", json.loads(checkpoint.read_text(encoding="utf-8")))


class PreindexExecutionTests(unittest.TestCase):
    def test_seeded_nonmatching_paper_skips_unusable_llm_extraction(self):
        calls = []

        def llm_chat(_messages, _timeout):
            calls.append(True)
            raise AssertionError("irrelevant paper must not reach the LLM")

        extractor = ReferenceMetadataExtractor(llm_chat=llm_chat, use_llm=True)
        papers, changed = extractor.enrich_papers(
            [{
                "paperId": "unrelated",
                "title": "An unrelated article",
                "abstract": "No matching target appears in this text.",
            }],
            seed_gene="TP53",
        )

        self.assertTrue(changed)
        self.assertEqual(calls, [])
        self.assertTrue(papers[0]["entity_extraction_complete"])

    def test_gene_preindex_builds_general_and_primary_pools_and_is_idempotent(self):
        s2 = FakeS2()
        rag = FakeRAG()
        first = preindex_gene(gene="TP53", s2_agent=s2, rag_agent=rag)
        second = preindex_gene(gene="TP53", s2_agent=s2, rag_agent=rag)

        self.assertEqual(first["status"], "completed")
        self.assertEqual(len(s2.calls), 2)
        self.assertEqual(len(rag.docs), 2)
        self.assertEqual(
            [pool["status"] for pool in second["pools"].values()],
            ["already_indexed", "already_indexed"],
        )

    def test_exhausted_rate_limit_opens_breaker_before_second_pool(self):
        s2 = FailingS2(429)
        result = preindex_gene(gene="TP53", s2_agent=s2, rag_agent=FakeRAG())

        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["halt_sweep"])
        self.assertEqual(result["circuit_breaker_reason"]["status_code"], 429)
        self.assertEqual([call[1] for call in s2.calls], [None])
        self.assertNotIn("primary", result["pools"])

    def test_nontransient_query_error_does_not_open_breaker(self):
        s2 = FailingS2(400)
        result = preindex_gene(gene="TP53", s2_agent=s2, rag_agent=FakeRAG())

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["halt_sweep"])
        self.assertEqual([call[1] for call in s2.calls], [None, "breast cancer"])


class SemanticScholarRetryTests(unittest.TestCase):
    def make_agent(self):
        agent = SemanticScholarAgent(api_key="test", cache_dir=None)
        agent._respect_api_key_rate_limit = lambda: None
        return agent

    @patch("agents.semantic_scholar.time.sleep", return_value=None)
    @patch("agents.semantic_scholar.requests.get")
    def test_first_429_stops_retries_and_preserves_retry_after(self, mock_get, _sleep):
        mock_get.return_value = FakeResponse(429, headers={"Retry-After": "37"})
        agent = self.make_agent()

        self.assertIsNone(agent.search("TP53", max_retries=5))
        health = agent.get_health_status()
        self.assertEqual(health["last_status_code"], 429)
        self.assertEqual(health["last_retry_after_seconds"], 37.0)
        self.assertEqual(health["api_key_status"], "rate_limited")
        self.assertEqual(mock_get.call_count, 1)
        _sleep.assert_not_called()

    @patch("agents.semantic_scholar.time.sleep", return_value=None)
    @patch("agents.semantic_scholar.requests.get")
    def test_500_is_retried_and_can_recover(self, mock_get, _sleep):
        mock_get.side_effect = [
            FakeResponse(500),
            FakeResponse(200, data={"data": [{"paperId": "ok"}]}),
        ]
        agent = self.make_agent()
        progress = []

        papers = agent.search("TP53", max_retries=5, progress_callback=progress.append)
        self.assertEqual([paper["paperId"] for paper in papers], ["ok"])
        self.assertEqual(mock_get.call_count, 2)
        self.assertIn(
            'Sending query to Semantic Scholar: "TP53" (API key)',
            progress,
        )
        self.assertIn('Semantic Scholar returned 1 papers for "TP53"', progress)

    @patch("agents.semantic_scholar.time.sleep", return_value=None)
    @patch("agents.semantic_scholar.requests.get")
    def test_repeated_timeouts_preserve_network_failure(self, mock_get, _sleep):
        mock_get.side_effect = [requests.Timeout("timed out") for _ in range(5)]
        agent = self.make_agent()

        self.assertIsNone(agent.search("TP53", max_retries=5))
        health = agent.get_health_status()
        self.assertIsNone(health["last_status_code"])
        self.assertIn("timed out", health["last_error"])
        self.assertEqual(mock_get.call_count, 5)

    @patch("agents.semantic_scholar.time.sleep", return_value=None)
    @patch("agents.semantic_scholar.requests.get")
    def test_default_timeout_retry_budget_is_three(self, mock_get, _sleep):
        mock_get.side_effect = [requests.Timeout("timed out") for _ in range(3)]
        agent = self.make_agent()

        self.assertIsNone(agent.search("TP53"))
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(_sleep.call_count, 2)

    @patch("agents.semantic_scholar.time.sleep", return_value=None)
    @patch("agents.semantic_scholar.requests.get")
    def test_read_timeout_is_not_retried(self, mock_get, _sleep):
        mock_get.side_effect = requests.ReadTimeout("read timed out")
        agent = self.make_agent()

        self.assertIsNone(agent.search("TP53", max_retries=5, timeout=45))
        self.assertEqual(mock_get.call_count, 1)
        _sleep.assert_not_called()

    def test_retry_after_supports_http_date(self):
        now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(
            parse_retry_after_seconds("Mon, 31 Aug 2026 12:02:00 GMT", now=now),
            120.0,
        )


class CircuitBreakerCooldownTests(unittest.TestCase):
    def test_legacy_open_breaker_gets_persistent_cooldown(self):
        now = datetime(2026, 8, 31, 12, 2, tzinfo=timezone.utc)
        breaker = _normalize_open_breaker({
            "state": "open",
            "opened_at": "2026-08-31T12:00:00+00:00",
            "reason": {"status_code": 429, "gene": "TP53"},
        }, now=now)

        self.assertEqual(breaker["consecutive_rate_limits"], 1)
        self.assertEqual(breaker["cooldown_seconds"], 300.0)
        self.assertEqual(_cooldown_remaining_seconds(breaker, now=now), 180.0)

    def test_repeated_429_doubles_cooldown_and_honors_retry_after(self):
        now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
        first = _open_circuit_breaker(
            reason={"status_code": 429},
            now=now,
        )
        second = _open_circuit_breaker(
            reason={"status_code": 429, "retry_after_seconds": 4000},
            previous=first,
            now=now,
        )

        self.assertEqual(first["cooldown_seconds"], 300.0)
        self.assertEqual(second["consecutive_rate_limits"], 2)
        self.assertEqual(second["cooldown_seconds"], 4000.0)

    def test_old_policy_checkpoint_is_recalculated(self):
        now = datetime(2026, 8, 31, 12, 2, tzinfo=timezone.utc)
        breaker = _normalize_open_breaker({
            "state": "open",
            "policy_version": 1,
            "opened_at": "2026-08-31T12:00:00+00:00",
            "cooldown_until": "2026-08-31T12:30:00+00:00",
            "consecutive_rate_limits": 2,
            "reason": {"status_code": 429},
        }, now=now)

        self.assertEqual(breaker["policy_version"], 3)
        self.assertEqual(breaker["consecutive_rate_limits"], 1)
        self.assertEqual(breaker["cooldown_seconds"], 300.0)
        self.assertEqual(_cooldown_remaining_seconds(breaker, now=now), 180.0)

    def test_any_api_success_resets_consecutive_rate_limits(self):
        now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
        reset = _record_api_successes(
            {
                "state": "closed",
                "consecutive_rate_limits": 4,
                "successful_queries_since_rate_limit": 0,
            },
            1,
            now=now,
        )
        reopened = _open_circuit_breaker(
            reason={"status_code": 429},
            previous=reset,
            now=now,
        )

        self.assertEqual(reset["consecutive_rate_limits"], 0)
        self.assertEqual(reopened["consecutive_rate_limits"], 1)
        self.assertEqual(reopened["cooldown_seconds"], 300.0)

    def test_chroma_process_lock_rejects_a_second_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            first = acquire_chroma_process_lock(directory)
            try:
                with self.assertRaisesRegex(RuntimeError, "already open"):
                    acquire_chroma_process_lock(directory)
            finally:
                first.close()

            replacement = acquire_chroma_process_lock(directory)
            replacement.close()


if __name__ == "__main__":
    unittest.main()
