from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.semantic_scholar import SemanticScholarAgent
from reference_utils import (
    GENE_IDENTITY_POLICY_VERSION,
    ReferenceMetadataExtractor,
    build_reference_hit,
    gene_search_query,
    gene_search_strategies,
)


FALSE_GML_PAPERS = [
    {
        "paperId": "graph-learning",
        "title": "Towards a GML-Enabled Knowledge Graph Platform",
        "abstract": "Graph machine learning (GML) is provided as a service for knowledge graphs.",
        "citationCount": 5,
    },
    {
        "paperId": "chemical",
        "title": "Micellar-type aggregates of a GML inclusion complex",
        "abstract": "Glycerol monolaurate (GML) was encapsulated for antibacterial use.",
        "citationCount": 11,
    },
    {
        "paperId": "uav",
        "title": "YOLO-GML for UAV aerial images",
        "abstract": "The YOLO-GML object detector improves edge information in aerial images.",
        "citationCount": 7,
    },
]


class GeneIdentityValidationTests(unittest.TestCase):
    def test_ambiguous_gene_query_uses_official_identity(self):
        self.assertEqual(
            gene_search_query("GML", "gastric cancer"),
            "GML glycosylphosphatidylinositol anchored molecule like LY6DL gastric cancer",
        )
        self.assertEqual(gene_search_query("TP53", None), "TP53")

    def test_recall_strategies_add_aliases_and_broad_queries(self):
        self.assertEqual(
            [item["query"] for item in gene_search_strategies("GML", "gastric cancer")],
            [
                "GML glycosylphosphatidylinositol anchored molecule like LY6DL gastric cancer",
                "GML glycosylphosphatidylinositol anchored molecule like LY6DL stomach cancer",
                "GML gene gastric cancer",
                "GML gastric cancer",
            ],
        )
        self.assertEqual(
            [item["query"] for item in gene_search_strategies("CDKAL1", "type 2 diabetes")],
            [
                "CDKAL1 type 2 diabetes",
                "CDKAL1 t2d",
                "CDKAL1 type ii diabetes",
            ],
        )

    def test_acronym_collisions_fail_closed_without_semantic_validation(self):
        agent = SemanticScholarAgent(api_key="")
        papers = [dict(paper) for paper in FALSE_GML_PAPERS]

        docs = agent.papers_to_docs("GML", papers)

        self.assertEqual(docs, [])
        self.assertTrue(all(
            paper["gene_identity_validated"] is False
            for paper in papers
        ))

    def test_official_gene_name_is_accepted_deterministically(self):
        paper = {
            "paperId": "real-gml",
            "title": "Genomic structure of GML",
            "abstract": (
                "GML is a glycosylphosphatidylinositol anchored molecule like gene "
                "induced by wildtype p53."
            ),
            "citationCount": 10,
        }
        agent = SemanticScholarAgent(api_key="")

        docs = agent.papers_to_docs("GML", [paper])

        self.assertEqual(len(docs), 1)
        self.assertTrue(docs[0]["meta"]["gene_identity_validated"])
        self.assertEqual(
            docs[0]["meta"]["gene_identity_policy_version"],
            GENE_IDENTITY_POLICY_VERSION,
        )

    def test_semantic_validator_can_reject_an_ambiguous_symbol(self):
        extractor = ReferenceMetadataExtractor(
            llm_chat=lambda _messages, _timeout: json.dumps({
                "items": [{
                    "paper_id": "graph-learning",
                    "genes": [],
                    "phenotypes": [],
                }]
            }),
            use_llm=True,
        )
        papers, _ = extractor.enrich_papers(
            [dict(FALSE_GML_PAPERS[0])],
            seed_gene="GML",
        )

        self.assertTrue(papers[0]["entity_extraction_complete"])
        self.assertFalse(papers[0]["gene_identity_validated"])
        self.assertEqual(papers[0]["gene_identity_method"], "semantic_rejection")

    def test_stale_cache_query_is_refreshed_with_disambiguated_query(self):
        genuine = {
            "paperId": "real-gml",
            "title": "Genomic structure of GML",
            "abstract": "The GML glycosylphosphatidylinositol anchored molecule like gene is induced by p53.",
            "citationCount": 10,
        }
        with tempfile.TemporaryDirectory() as directory:
            agent = SemanticScholarAgent(api_key="test", cache_dir=Path(directory))
            cache_path = agent.cache_path_for_gene("GML")
            agent._write_cache_payload(cache_path, {
                "gene": "GML",
                "phenotype": None,
                "query": "GML",
                "fetch_ok": True,
                "data": [dict(FALSE_GML_PAPERS[0])],
            })

            with patch.object(agent, "search", return_value=[genuine]) as search:
                papers = agent.cached_for_gene("GML", limit=10)

            self.assertEqual(papers[0]["paperId"], "real-gml")
            self.assertEqual(
                search.call_args.args[0],
                gene_search_query("GML"),
            )
            self.assertTrue(agent.cached_query_succeeded("GML"))

    def test_final_reference_gate_rejects_legacy_semantic_scholar_metadata(self):
        text = "GML paper\n\nGML is discussed in this abstract."
        legacy_meta = {
            "source": "semanticscholar",
            "paperId": "legacy",
            "title": "GML paper",
            "citationCount": 2,
            "extracted_genes": "GML",
        }

        self.assertIsNone(build_reference_hit(text, legacy_meta, gene="GML"))


if __name__ == "__main__":
    unittest.main()
