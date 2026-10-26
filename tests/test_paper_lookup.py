import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from agents.rag import RAGAgent
from agents.semantic_scholar import SemanticScholarAgent
from routes.plots import get_paper


class _Collection:
    def __init__(self, rows):
        self.rows = rows

    def get(self, *, where, include):
        selected = [
            row
            for row in self.rows
            if str(row[1].get(next(iter(where)), "")) == str(next(iter(where.values())))
        ]
        return {
            "documents": [row[0] for row in selected],
            "metadatas": [row[1] for row in selected],
        }


class IndexedPaperLookupTests(unittest.TestCase):
    def test_finds_prefixed_publication_by_bare_identifier(self):
        rag = object.__new__(RAGAgent)
        rag._collection = _Collection(
            [
                (
                    "A useful title\n\nThe indexed abstract.",
                    {
                        "gene": "GENE1",
                        "publication_id": "PMID:12345",
                        "pmid": "12345",
                        "title": "A useful title",
                        "journal": "Example Journal",
                        "authors": "A Author, B Author",
                        "year": 2025,
                        "citationCount": 7,
                        "url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
                    },
                )
            ]
        )

        paper = rag.find_indexed_paper("12345", ["GENE1"])

        self.assertIsNotNone(paper)
        self.assertEqual(paper["paperId"], "PMID:12345")
        self.assertEqual(paper["abstract"], "The indexed abstract.")
        self.assertEqual(paper["journal"], "Example Journal")
        self.assertEqual(paper["pmid"], "12345")

    def test_returns_none_for_a_different_publication(self):
        rag = object.__new__(RAGAgent)
        rag._collection = _Collection(
            [("Title\n\nAbstract", {"gene": "GENE1", "publication_id": "PMID:1"})]
        )

        self.assertIsNone(rag.find_indexed_paper("PMID:2", ["GENE1"]))

    def test_exact_identifier_fallback_handles_a_stale_gene_label(self):
        rag = object.__new__(RAGAgent)
        rag._collection = _Collection(
            [
                (
                    "Title\n\nAbstract",
                    {
                        "gene": "ORIGINAL_GENE",
                        "publication_id": "PMID:42",
                        "pmid": "42",
                        "title": "Title",
                    },
                ),
                (
                    "Another\n\nAbstract",
                    {
                        "gene": "DISPLAY_GENE",
                        "publication_id": "PMID:7",
                        "pmid": "7",
                        "title": "Another",
                    },
                ),
            ]
        )

        paper = rag.find_indexed_paper("PMID:42", ["DISPLAY_GENE"])

        self.assertIsNotNone(paper)
        self.assertEqual(paper["paperId"], "PMID:42")

    def test_route_prefers_the_index_without_touching_provider_caches(self):
        indexed = {"paperId": "PMID:99", "title": "Indexed", "abstract": "Stored"}
        rag = Mock()
        rag.find_indexed_paper.return_value = indexed

        with (
            patch("routes.plots.get_rag_agent", return_value=rag),
            patch("routes.plots.get_europe_pmc_agent") as get_epmc,
            patch("routes.plots.get_s2_agent") as get_s2,
        ):
            result = get_paper(paper_id="PMID:99", gene="GENE1")

        self.assertEqual(result, indexed)
        get_epmc.assert_not_called()
        get_s2.assert_not_called()


class SemanticScholarCacheLookupTests(unittest.TestCase):
    def test_cache_lookup_accepts_a_pubmed_identifier_without_requesting(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            cache_dir = Path(temporary_dir)
            agent = SemanticScholarAgent(api_key="test", cache_dir=cache_dir)
            cache_path = agent.cache_path_for_gene("GENE1")
            cache_path.write_text(
                json.dumps(
                    {
                        "data": [
                            {
                                "paperId": "s2-id",
                                "externalIds": {"PubMed": "456", "DOI": "10.1/example"},
                                "title": "Cached paper",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            paper = agent.find_cached_paper("PMID:456", ["GENE1"])

        self.assertIsNotNone(paper)
        self.assertEqual(paper["paperId"], "s2-id")


if __name__ == "__main__":
    unittest.main()
