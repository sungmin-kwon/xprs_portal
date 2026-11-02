from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.europe_pmc import EuropePMCAgent
from agents.evidence_assembly import EvidenceAssemblyAgent
from reference_utils import ReferenceMetadataExtractor, build_reference_hit


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class EuropePMCTests(unittest.TestCase):
    def make_agent(self, root: Path) -> EuropePMCAgent:
        return EuropePMCAgent(
            cache_dir=root,
            metadata_extractor=ReferenceMetadataExtractor(use_llm=False),
        )

    @patch("agents.europe_pmc.requests.get")
    def test_public_search_is_cached_and_normalized(self, mock_get):
        mock_get.return_value = FakeResponse({
            "resultList": {"result": [{
                "source": "MED", "id": "123", "pmid": "123",
                "title": "TP53 in cancer", "abstractText": "TP53 regulates cell-cycle checkpoints.",
                "pubYear": "2025", "journalInfo": {"journal": {"title": "Example Journal"}},
                "authorString": "Example A, Example B.", "citedByCount": 7,
            }]}
        })
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make_agent(Path(directory))
            first = agent.cached_for_gene("TP53", phenotype="gastric cancer")
            second = agent.cached_for_gene("TP53", phenotype="gastric cancer")

        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(first, second)
        self.assertEqual(first[0]["publication_id"], "PMID:123")
        self.assertEqual(first[0]["url"], "https://pubmed.ncbi.nlm.nih.gov/123/")
        self.assertEqual(first[0]["provider_url"], "https://europepmc.org/article/MED/123")
        self.assertEqual(first[0]["journal"], "Example Journal")
        self.assertEqual(first[0]["year"], "2025")
        self.assertTrue(first[0]["gene_identity_validated"])

    @patch("agents.europe_pmc.requests.get")
    def test_cached_eligible_count_matches_document_policy(self, mock_get):
        mock_get.return_value = FakeResponse({
            "resultList": {"result": [
                {
                    "source": "MED", "id": "123", "pmid": "123",
                    "title": "TP53 cited evidence", "abstractText": "TP53 evidence.",
                    "citedByCount": 4,
                },
                {
                    "source": "MED", "id": "456", "pmid": "456",
                    "title": "TP53 uncited evidence", "abstractText": "TP53 evidence.",
                    "citedByCount": 0,
                },
            ]}
        })
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make_agent(Path(directory))
            papers = agent.cached_for_gene("TP53")
            payload = agent._read_json(agent._cache_path("TP53", None))
            docs = agent.papers_to_docs("TP53", papers)

        self.assertEqual(payload["eligible_count"], 1)
        self.assertEqual(len(docs), 1)

    def test_documents_use_shared_source_neutral_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make_agent(Path(directory))
            docs = agent.papers_to_docs("TP53", [{
                "publication_id": "PMID:123", "paperId": "PMID:123", "pmid": "123",
                "title": "TP53 evidence", "abstract": "TP53 is associated with disease.",
                "citationCount": 4,
            }], pool_type="general")

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["meta"]["source"], "europe_pmc")
        self.assertEqual(docs[0]["meta"]["publication_id"], "PMID:123")
        self.assertEqual(docs[0]["meta"]["pool_type"], "general")
        self.assertTrue(build_reference_hit(docs[0]["text"], docs[0]["meta"], gene="TP53"))

    def test_cached_paper_lookup_does_not_require_network(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make_agent(Path(directory))
            path = agent._cache_path("TP53", None)
            agent._write_json(path, {"fetch_ok": True, "data": [{
                "publication_id": "PMID:123", "paperId": "PMID:123",
                "pmid": "123", "title": "TP53 evidence",
            }]})

            paper = agent.find_cached_paper("123", ["A_DIFFERENT_GENE"])

        self.assertIsNotNone(paper)
        self.assertEqual(paper["pmid"], "123")

    def test_any_eligible_europe_pmc_result_avoids_automatic_s2_fallback(self):
        class FailingS2:
            def __init__(self):
                self.called = False
            def cached_query_succeeded(self, _gene, _phenotype=None):
                return False
            def cached_for_gene(self, *_args, **_kwargs):
                self.called = True
                return []
            def papers_to_docs(self, *_args, **_kwargs):
                return []
            def get_health_status(self):
                return {"last_status_code": 429}

        class WorkingEurope:
            def cached_query_succeeded(self, _gene, _phenotype=None):
                return True
            def cached_for_gene(self, *_args, **_kwargs):
                return [{"publication_id": "PMID:123"}]
            def papers_to_docs(self, gene, _papers, pool_type, phenotype=None):
                return [{"id": "epmc-doc", "text": "TP53\n\nEvidence", "meta": {
                    "source": "europe_pmc", "gene": gene, "pool_type": pool_type,
                    "phenotype": phenotype, "publication_id": "PMID:123",
                    "gene_identity_policy_version": 2, "gene_identity_validated": True,
                }}]

        class MemoryRAG:
            def __init__(self):
                self.docs = []
            def has_documents(self, where):
                clauses = where.get("$and", [where])
                return any(all(all(doc["meta"].get(k) == v for k, v in clause.items()) for clause in clauses) for doc in self.docs)
            def upsert_docs(self, docs):
                self.docs.extend(docs)

        rag = MemoryRAG()
        s2 = FailingS2()
        evidence = EvidenceAssemblyAgent(
            rag_agent=rag, ot_agent=None, s2_agent=s2, europe_pmc_agent=WorkingEurope()
        )
        completed = evidence._fetch_and_index_pool(
            "TP53", pool_type="general", phenotype=None, limit=10, progress_callback=None
        )
        self.assertTrue(completed)
        self.assertFalse(s2.called)
        self.assertEqual(rag.docs[0]["meta"]["source"], "europe_pmc")

    def test_europe_pmc_stops_before_semantic_scholar_at_interactive_target(self):
        class UnexpectedS2:
            def __init__(self):
                self.called = False
            def cached_query_succeeded(self, _gene, _phenotype=None):
                return False
            def cached_for_gene(self, *_args, **_kwargs):
                self.called = True
                raise AssertionError("Semantic Scholar should not be queried")
            def papers_to_docs(self, *_args, **_kwargs):
                return []

        class WorkingEurope:
            def cached_query_succeeded(self, _gene, _phenotype=None):
                return True
            def cached_for_gene(self, *_args, **_kwargs):
                return [{"publication_id": f"PMID:{index}"} for index in range(5)]
            def papers_to_docs(self, gene, papers, pool_type, phenotype=None):
                return [{"id": f"epmc-{index}", "text": "TP53\n\nEvidence", "meta": {
                    "source": "europe_pmc", "gene": gene, "pool_type": pool_type,
                    "phenotype": phenotype, "publication_id": paper["publication_id"],
                    "gene_identity_policy_version": 2, "gene_identity_validated": True,
                }} for index, paper in enumerate(papers)]

        class MemoryRAG:
            def __init__(self):
                self.docs = []
            def upsert_docs(self, docs):
                self.docs.extend(docs)

        s2 = UnexpectedS2()
        rag = MemoryRAG()
        evidence = EvidenceAssemblyAgent(
            rag_agent=rag, ot_agent=None, s2_agent=s2, europe_pmc_agent=WorkingEurope()
        )
        completed = evidence._fetch_and_index_pool(
            "TP53", pool_type="general", phenotype=None, limit=10, progress_callback=None
        )

        self.assertTrue(completed)
        self.assertFalse(s2.called)
        self.assertEqual(len(rag.docs), 5)

    def test_disease_specific_europe_pmc_hit_prevents_general_s2_fallback(self):
        class UnexpectedS2:
            def __init__(self):
                self.called = False
            def cached_query_succeeded(self, _gene, _phenotype=None):
                return False
            def cached_papers(self, _gene, _phenotype=None):
                return []
            def cached_for_gene(self, *_args, **_kwargs):
                self.called = True
                raise AssertionError("Semantic Scholar should not be queried")
            def papers_to_docs(self, *_args, **_kwargs):
                return []

        class PhenotypeOnlyEurope:
            def cached_query_succeeded(self, _gene, _phenotype=None):
                return True
            def cached_papers(self, _gene, phenotype=None):
                return [{"publication_id": "PMID:123"}] if phenotype else []
            def cached_for_gene(self, _gene, *, phenotype=None, **_kwargs):
                return [{"publication_id": "PMID:123"}] if phenotype else []
            def papers_to_docs(self, gene, papers, pool_type, phenotype=None):
                if not papers:
                    return []
                return [{"id": "epmc-phenotype", "text": "TP53 disease evidence", "meta": {
                    "source": "europe_pmc", "gene": gene, "pool_type": pool_type,
                    "phenotype": phenotype, "publication_id": "PMID:123",
                    "gene_identity_policy_version": 2, "gene_identity_validated": True,
                }}]

        class MemoryRAG:
            def __init__(self):
                self.docs = []
            def has_documents(self, where):
                clauses = where.get("$and", [where])
                return any(
                    all(all(doc["meta"].get(k) == v for k, v in clause.items()) for clause in clauses)
                    for doc in self.docs
                )
            def upsert_docs(self, docs):
                self.docs.extend(docs)

        s2 = UnexpectedS2()
        rag = MemoryRAG()
        evidence = EvidenceAssemblyAgent(
            rag_agent=rag,
            ot_agent=None,
            s2_agent=s2,
            europe_pmc_agent=PhenotypeOnlyEurope(),
        )

        evidence._ensure_indexed_for_gene("TP53")

        self.assertFalse(s2.called)
        self.assertEqual([doc["meta"]["pool_type"] for doc in rag.docs], ["phenotype"])

    def test_general_pool_with_primary_evidence_skips_second_epmc_query(self):
        class UnexpectedS2:
            def cached_query_succeeded(self, _gene, _phenotype=None):
                return False
            def cached_papers(self, _gene, _phenotype=None):
                return []
            def papers_to_docs(self, *_args, **_kwargs):
                return []

        class CoveredEurope:
            def __init__(self):
                self.live_queries = []
            def cached_query_succeeded(self, _gene, phenotype=None):
                return phenotype is None
            def cached_papers(self, _gene, phenotype=None):
                if phenotype is not None:
                    return []
                return [{"publication_id": f"PMID:{index}"} for index in range(5)]
            def cached_for_gene(self, _gene, *, phenotype=None, **_kwargs):
                self.live_queries.append(phenotype)
                return self.cached_papers(_gene, phenotype)
            def papers_to_docs(self, gene, papers, pool_type, phenotype=None):
                return [{
                    "id": f"epmc-{index}",
                    "text": "TP53 breast cancer evidence",
                    "meta": {
                        "source": "europe_pmc",
                        "gene": gene,
                        "pool_type": pool_type,
                        "phenotype": phenotype,
                        "publication_id": paper["publication_id"],
                        "extracted_phenotypes": ["breast cancer"] if index < 2 else [],
                        "gene_identity_policy_version": 2,
                        "gene_identity_validated": True,
                    },
                } for index, paper in enumerate(papers)]

        class MemoryRAG:
            def __init__(self, docs):
                self.docs = docs
            def has_documents(self, where):
                clauses = where.get("$and", [where])
                return any(
                    all(all(doc["meta"].get(k) == v for k, v in clause.items()) for clause in clauses)
                    for doc in self.docs
                )
            def upsert_docs(self, docs):
                self.docs.extend(docs)

        europe = CoveredEurope()
        cached_docs = europe.papers_to_docs(
            "TP53", europe.cached_papers("TP53"), "general"
        )
        evidence = EvidenceAssemblyAgent(
            rag_agent=MemoryRAG(cached_docs),
            ot_agent=None,
            s2_agent=UnexpectedS2(),
            europe_pmc_agent=europe,
        )

        evidence._ensure_indexed_for_gene("TP53")

        self.assertEqual(europe.live_queries, [])
        self.assertTrue(evidence._general_pool_covers_primary("TP53"))

    def test_manual_continue_search_queries_s2_after_sparse_epmc_result(self):
        class SparseEurope:
            source_name = "europe_pmc"
            def cached_query_succeeded(self, _gene, _phenotype=None):
                return True
            def cached_papers(self, _gene, _phenotype=None):
                return [{"publication_id": "PMID:123"}]
            def cached_for_gene(self, *_args, **_kwargs):
                return self.cached_papers("TP53")
            def papers_to_docs(self, gene, _papers, pool_type, phenotype=None):
                return [{"id": "epmc-doc", "text": "TP53\n\nEvidence", "meta": {
                    "source": "europe_pmc", "gene": gene, "pool_type": pool_type,
                    "phenotype": phenotype, "publication_id": "PMID:123",
                    "pmid": "123", "gene_identity_policy_version": 2,
                    "gene_identity_validated": True,
                }}]

        class FallbackS2:
            source_name = "semanticscholar"
            def __init__(self):
                self.cached = False
                self.called = False
            def cached_query_succeeded(self, _gene, _phenotype=None):
                return self.cached
            def cached_papers(self, _gene, _phenotype=None):
                return []
            def cached_for_gene(self, *_args, **_kwargs):
                self.called = True
                self.cached = True
                return []
            def papers_to_docs(self, *_args, **_kwargs):
                return []
            def pagination_status(self, *_args, **_kwargs):
                return {
                    "fetch_ok": self.cached,
                    "pagination_complete": False,
                    "enrichment_complete": False,
                }
            def get_health_status(self):
                return {"last_status_code": 200}

        class MemoryRAG:
            def __init__(self):
                self.docs = [{"id": "existing", "meta": {
                    "source": "europe_pmc", "gene": "TP53",
                    "pool_type": "general", "phenotype": None,
                }}]
            def has_documents(self, _where):
                return bool(self.docs)
            def upsert_docs(self, docs):
                self.docs.extend(docs)

        s2 = FallbackS2()
        evidence = EvidenceAssemblyAgent(
            rag_agent=MemoryRAG(),
            ot_agent=None,
            s2_agent=s2,
            europe_pmc_agent=SparseEurope(),
        )
        result = evidence.manually_index_pool("TP53")

        self.assertTrue(s2.called)
        self.assertTrue(result["documents_present"])
        self.assertIn(result["status"], {"already_indexed", "enrichment_pending"})


if __name__ == "__main__":
    unittest.main()
