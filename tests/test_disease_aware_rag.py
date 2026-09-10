from __future__ import annotations

import threading
import time
import unittest

import numpy as np

from agents.evidence_assembly import (
    NEUTRAL_INTENT,
    OTHER_INTENT,
    PRIMARY_INTENT,
    EvidenceAssemblyAgent,
)
from agents.query_analysis import QueryAnalysisAgent
from agents.rag import RAGAgent
from agents.semantic_scholar import SemanticScholarAgent


class FakeLLM:
    def __init__(self, response: str):
        self.response = response

    def chat(self, _messages):
        return self.response


class FakeReranker:
    def predict(self, _pairs, **_kwargs):
        return np.asarray([0.1, 0.9], dtype=np.float32)


class FakePolicyRAG:
    def rerank(self, _query, candidates):
        out = []
        for text, meta in candidates:
            enriched = dict(meta)
            enriched["reranker_score"] = enriched.pop("test_score")
            out.append((text, enriched))
        return sorted(out, key=lambda item: item[1]["reranker_score"], reverse=True)


class FakeIndexRAG:
    def __init__(self, documents=None):
        self.documents = list(documents or [])

    @staticmethod
    def _matches(metadata, where):
        clauses = where.get("$and", [where])
        return all(
            all(metadata.get(key) == value for key, value in clause.items())
            for clause in clauses
        )

    def has_documents(self, where):
        return any(self._matches(doc["meta"], where) for doc in self.documents)

    def upsert_docs(self, documents):
        self.documents.extend(documents)


class FakeIndexS2:
    def __init__(self, cached=None):
        self.cached = set(cached or [])
        self.calls = []

    def cached_query_succeeded(self, gene, phenotype=None):
        return (gene, phenotype) in self.cached

    def cached_for_gene(self, gene, limit, phenotype=None, progress_callback=None):
        self.calls.append((gene, phenotype, limit))
        self.cached.add((gene, phenotype))
        return [{"paperId": f"{gene}-{phenotype or 'general'}"}]

    def papers_to_docs(self, gene, papers, pool_type, phenotype=None):
        return [{
            "id": papers[0]["paperId"],
            "text": f"{gene} evidence",
            "meta": {
                "gene": gene,
                "pool_type": pool_type,
                "phenotype": phenotype,
            },
        }]


class FakeRateLimitedS2:
    def __init__(self):
        self.calls = []

    def cached_query_succeeded(self, _gene, _phenotype=None):
        return False

    def cached_for_gene(self, gene, limit, phenotype=None, progress_callback=None):
        self.calls.append((gene, phenotype, limit))
        return []

    def papers_to_docs(self, _gene, _papers, pool_type, phenotype=None):
        return []

    def get_health_status(self):
        return {
            "last_status_code": 429,
            "last_retry_after_seconds": None,
        }


class FakeIndexOT:
    def doc_for_gene(self, _gene):
        return None


def candidate(
    *,
    paper_id: str,
    title: str,
    abstract: str,
    score: float,
    phenotype: str,
) -> tuple[str, dict]:
    text = f"{title}\n\n{abstract}"
    return text, {
        "source": "semanticscholar",
        "gene": "GENE1",
        "pool_type": "phenotype" if phenotype else "general",
        "phenotype": phenotype,
        "paperId": paper_id,
        "title": title,
        "citationCount": 5,
        "extracted_phenotypes": phenotype,
        "test_score": score,
    }


class DiseaseIntentTests(unittest.TestCase):
    def analyze(self, question: str, response: str) -> dict:
        return QueryAnalysisAgent(FakeLLM(response)).analyze(
            question,
            available_genes=["GENE1"],
        )

    def test_neutral_gene_question_does_not_default_to_breast_cancer(self):
        result = self.analyze(
            "What does GENE1 do?",
            '{"rewritten_query":"GENE1 biological function","genes":["GENE1"],'
            '"phenotypes":[],"scope":"named_genes","disease_intent":"disease_neutral"}',
        )
        self.assertEqual(result["disease_intent"], NEUTRAL_INTENT)
        self.assertEqual(result["phenotypes"], [])

    def test_explicit_korean_other_disease_is_canonicalized(self):
        result = self.analyze(
            "GENE1은 갑상선암과 관련이 있나요?",
            '{"rewritten_query":"GENE1 thyroid cancer association","genes":["GENE1"],'
            '"phenotypes":["thyroid cancer"],"scope":"named_genes",'
            '"disease_intent":"other_disease"}',
        )
        self.assertEqual(result["disease_intent"], OTHER_INTENT)
        self.assertEqual(result["phenotypes"], ["thyroid cancer"])

    def test_broad_other_disease_query_does_not_infer_primary(self):
        result = self.analyze(
            "What other diseases are associated with GENE1?",
            '{"rewritten_query":"GENE1 associations with other diseases",'
            '"genes":["GENE1"],"phenotypes":[],"scope":"named_genes",'
            '"disease_intent":"other_disease"}',
        )
        self.assertEqual(result["disease_intent"], OTHER_INTENT)
        self.assertNotIn("breast cancer", result["phenotypes"])

    def test_named_disease_outside_alias_catalog_is_retained(self):
        result = self.analyze(
            "Is GENE1 associated with Behcet disease?",
            '{"rewritten_query":"GENE1 Behcet disease association",'
            '"genes":["GENE1"],"phenotypes":["Behcet disease"],'
            '"scope":"named_genes","disease_intent":"other_disease"}',
        )
        self.assertEqual(result["disease_intent"], OTHER_INTENT)
        self.assertEqual(result["phenotypes"], ["behcet disease"])


class PolicyRankingTests(unittest.TestCase):
    def setUp(self):
        self.agent = EvidenceAssemblyAgent(FakePolicyRAG(), None, None)

    def rank(self, rows, intent, targets):
        return self.agent._rank_candidates(
            gene="GENE1",
            query="GENE1 evidence",
            candidates=rows,
            intent=intent,
            targets=targets,
            broad_other=False,
            broad_cancers_only=False,
            top_k=10,
        )

    def test_broad_other_diseases_treats_non_cancer_disease_as_direct(self):
        match = self.agent._disease_match(
            ["rheumatoid arthritis"],
            intent=OTHER_INTENT,
            targets=[],
            broad_other=True,
            broad_cancers_only=False,
        )
        self.assertEqual(match, "direct")

    def test_broad_other_cancers_does_not_treat_non_cancer_as_direct(self):
        match = self.agent._disease_match(
            ["rheumatoid arthritis"],
            intent=OTHER_INTENT,
            targets=[],
            broad_other=True,
            broad_cancers_only=True,
        )
        self.assertEqual(match, "related")

    def test_primary_boost_is_soft_not_a_hard_quota(self):
        breast = candidate(
            paper_id="breast",
            title="GENE1 in breast cancer",
            abstract="GENE1 breast cancer evidence.",
            score=0.60,
            phenotype="breast cancer",
        )
        strong_other = candidate(
            paper_id="thyroid",
            title="GENE1 in thyroid cancer",
            abstract="GENE1 thyroid cancer evidence.",
            score=0.90,
            phenotype="thyroid cancer",
        )
        _, refs, _ = self.rank([breast, strong_other], PRIMARY_INTENT, ["breast cancer"])
        self.assertEqual(refs[0]["paperId"], "thyroid")
        self.assertEqual(refs[1]["disease_match"], "direct")

    def test_direct_primary_evidence_wins_when_relevance_is_close(self):
        breast = candidate(
            paper_id="breast",
            title="GENE1 in breast cancer",
            abstract="GENE1 breast cancer evidence.",
            score=0.80,
            phenotype="breast cancer",
        )
        other = candidate(
            paper_id="thyroid",
            title="GENE1 in thyroid cancer",
            abstract="GENE1 thyroid cancer evidence.",
            score=0.90,
            phenotype="thyroid cancer",
        )
        _, refs, _ = self.rank([breast, other], PRIMARY_INTENT, ["breast cancer"])
        self.assertEqual(refs[0]["paperId"], "breast")

    def test_explicit_other_disease_overrides_primary_preference(self):
        thyroid = candidate(
            paper_id="thyroid",
            title="GENE1 in thyroid cancer",
            abstract="GENE1 thyroid cancer evidence.",
            score=0.80,
            phenotype="thyroid cancer",
        )
        breast = candidate(
            paper_id="breast",
            title="GENE1 in breast cancer",
            abstract="GENE1 breast cancer evidence.",
            score=0.90,
            phenotype="breast cancer",
        )
        _, refs, _ = self.rank([thyroid, breast], OTHER_INTENT, ["thyroid cancer"])
        self.assertEqual(refs[0]["paperId"], "thyroid")
        self.assertEqual(refs[0]["disease_match"], "direct")


class EvidenceIndexProgressTests(unittest.TestCase):
    @staticmethod
    def document(gene, pool_type, phenotype=None):
        return {
            "id": f"{gene}-{pool_type}-{phenotype or 'general'}",
            "text": f"{gene} evidence",
            "meta": {
                "gene": gene,
                "pool_type": pool_type,
                "phenotype": phenotype,
            },
        }

    def test_reports_when_both_query_pools_are_already_in_vector_store(self):
        rag = FakeIndexRAG([
            self.document("GENE1", "general"),
            self.document("GENE1", "phenotype", "breast cancer"),
        ])
        s2 = FakeIndexS2()
        agent = EvidenceAssemblyAgent(rag, FakeIndexOT(), s2)
        progress = []

        agent._ensure_indexed_for_gene("GENE1", progress_callback=progress.append)

        self.assertEqual(s2.calls, [])
        self.assertTrue(any("is indexed" in message for message in progress))
        self.assertTrue(any("general query and breast cancer query pools" in message for message in progress))

    def test_distinguishes_cached_rebuild_from_required_api_query(self):
        general = self.document("GENE1", "general")
        cached_s2 = FakeIndexS2(cached={("GENE1", "breast cancer")})
        cached_agent = EvidenceAssemblyAgent(
            FakeIndexRAG([general]), FakeIndexOT(), cached_s2
        )
        cached_progress = []
        cached_agent._ensure_indexed_for_gene(
            "GENE1", progress_callback=cached_progress.append
        )
        self.assertTrue(any("loading cached Semantic Scholar results" in message for message in cached_progress))

        live_s2 = FakeIndexS2()
        live_agent = EvidenceAssemblyAgent(
            FakeIndexRAG([general]), FakeIndexOT(), live_s2
        )
        live_progress = []
        live_agent._ensure_indexed_for_gene(
            "GENE1", progress_callback=live_progress.append
        )
        self.assertTrue(any("a Semantic Scholar query is required" in message for message in live_progress))

    def test_rate_limit_stops_remaining_queries_and_opens_runtime_cooldown(self):
        s2 = FakeRateLimitedS2()
        agent = EvidenceAssemblyAgent(FakeIndexRAG(), FakeIndexOT(), s2)
        progress = []

        agent._ensure_indexed_for_gene("GENE1", progress_callback=progress.append)
        agent._ensure_indexed_for_gene("GENE2", progress_callback=progress.append)

        self.assertEqual(len(s2.calls), 1)
        self.assertEqual(s2.calls[0][0:2], ("GENE1", None))
        self.assertEqual(agent._s2_rate_limit_streak, 1)
        self.assertTrue(any("Skipping the breast cancer query" in message for message in progress))
        self.assertTrue(any("rate-limit cooldown active" in message for message in progress))

    def test_repeated_rate_limits_double_the_runtime_cooldown(self):
        s2 = FakeRateLimitedS2()
        agent = EvidenceAssemblyAgent(FakeIndexRAG(), FakeIndexOT(), s2)

        agent._ensure_indexed_for_gene("GENE1")
        first_remaining = agent._s2_cooldown_until - time.monotonic()
        agent._s2_cooldown_until = 0.0
        agent._ensure_indexed_for_gene("GENE2")
        second_remaining = agent._s2_cooldown_until - time.monotonic()

        self.assertEqual(agent._s2_rate_limit_streak, 2)
        self.assertGreater(first_remaining, 59)
        self.assertGreater(second_remaining, 119)

    def test_successful_live_request_resets_rate_limit_streak(self):
        agent = EvidenceAssemblyAgent(
            FakeIndexRAG(), FakeIndexOT(), FakeIndexS2()
        )
        agent._s2_rate_limit_streak = 3

        agent._ensure_indexed_for_gene("GENE1")

        self.assertEqual(agent._s2_rate_limit_streak, 0)
        self.assertEqual(agent._s2_cooldown_until, 0.0)


class RerankerTests(unittest.TestCase):
    def test_reranker_reorders_dense_candidates_and_preserves_metadata(self):
        rag = RAGAgent.__new__(RAGAgent)
        rag._reranker_enabled = True
        rag._reranker = FakeReranker()
        rag._reranker_error = None
        rag._reranker_lock = threading.Lock()
        rag._reranker_batch_size = 8
        rag._load_reranker = lambda: rag._reranker
        ranked = rag.rerank(
            "query",
            [("first", {"paperId": "a"}), ("second", {"paperId": "b"})],
        )
        self.assertEqual([meta["paperId"] for _, meta in ranked], ["b", "a"])
        self.assertAlmostEqual(ranked[0][1]["reranker_score"], 0.9, places=5)


class IngestionHygieneTests(unittest.TestCase):
    def test_correction_and_retraction_notices_are_not_indexed(self):
        agent = SemanticScholarAgent(api_key="")
        papers = [
            {
                "paperId": "correction",
                "title": "Correction: GENE1 in breast cancer",
                "abstract": "GENE1 breast cancer.",
                "citationCount": 2,
            },
            {
                "paperId": "article",
                "title": "GENE1 in breast cancer",
                "abstract": "GENE1 breast cancer.",
                "citationCount": 2,
            },
        ]
        docs = agent.papers_to_docs(
            "GENE1", papers, pool_type="phenotype", phenotype="breast cancer"
        )
        self.assertEqual([doc["meta"]["paperId"] for doc in docs], ["article"])


if __name__ == "__main__":
    unittest.main()
