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

    def test_evidence_assembly_keeps_europe_pmc_results_when_s2_fallback_fails(self):
        class FailingS2:
            def cached_query_succeeded(self, _gene, _phenotype=None):
                return False
            def cached_for_gene(self, *_args, **_kwargs):
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
        evidence = EvidenceAssemblyAgent(
            rag_agent=rag, ot_agent=None, s2_agent=FailingS2(), europe_pmc_agent=WorkingEurope()
        )
        completed = evidence._fetch_and_index_pool(
            "TP53", pool_type="general", phenotype=None, limit=10, progress_callback=None
        )
        self.assertTrue(completed)
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


if __name__ == "__main__":
    unittest.main()
