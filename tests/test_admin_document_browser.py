from __future__ import annotations

import unittest
import threading

from agents.rag import RAGAgent
from tests.support import ROOT


class FakeCollection:
    def __init__(self):
        self.rows = [
            {
                "id": "s2::general::GENE1::a",
                "document": "GENE1 has a general biological function.",
                "metadata": {
                    "gene": "GENE1",
                    "pool_type": "general",
                    "source": "europe_pmc",
                    "paperId": "a",
                    "title": "General GENE1 paper",
                    "citationCount": 5,
                    "extracted_phenotypes": '["type 2 diabetes"]',
                },
            },
            {
                "id": "s2::phenotype::GENE1::b",
                "document": "GENE1 is studied in breast cancer.",
                "metadata": {
                    "gene": "GENE1",
                    "pool_type": "phenotype",
                    "phenotype": "breast cancer",
                    "source": "semanticscholar",
                    "paperId": "b",
                    "title": "Breast cancer and GENE1",
                    "citationCount": 20,
                },
            },
            {
                "id": "ot::GENE1",
                "document": "Open Targets association for GENE1.",
                "metadata": {"gene": "GENE1", "source": "opentargets"},
            },
            {
                "id": "s2::general::GENE2::c",
                "document": "GENE2 text.",
                "metadata": {
                    "gene": "GENE2",
                    "pool_type": "general",
                    "source": "semanticscholar",
                    "paperId": "c",
                    "title": "GENE2 paper",
                    "citationCount": 2,
                },
            },
        ]

    def get(self, where=None, include=None, ids=None, **_kwargs):
        rows = self.rows
        if ids is not None:
            wanted = set(ids)
            rows = [row for row in rows if row["id"] in wanted]
        if where:
            rows = [
                row
                for row in rows
                if all(row["metadata"].get(key) == value for key, value in where.items())
            ]
        return {
            "ids": [row["id"] for row in rows],
            "documents": [row["document"] for row in rows]
            if "documents" in (include or [])
            else None,
            "metadatas": [row["metadata"] for row in rows]
            if "metadatas" in (include or [])
            else None,
        }

    def delete(self, ids=None, where=None):
        if ids is not None:
            wanted = set(ids)
            self.rows = [row for row in self.rows if row["id"] not in wanted]
        elif where:
            self.rows = [
                row for row in self.rows
                if not all(row["metadata"].get(key) == value for key, value in where.items())
            ]


class AdminDocumentBrowserTests(unittest.TestCase):
    def setUp(self):
        self.rag = RAGAgent.__new__(RAGAgent)
        self.rag._collection = FakeCollection()
        self.rag._upsert_lock = threading.Lock()

    def test_inventory_groups_documents_by_gene_and_pool(self):
        inventory = self.rag.document_inventory()
        self.assertEqual(inventory["document_count"], 4)
        self.assertEqual(inventory["gene_count"], 2)
        self.assertEqual(
            inventory["pools"],
            {"general": 2, "opentargets": 1, "phenotype": 1},
        )
        self.assertEqual(inventory["phenotypes"], {"breast cancer": 1})
        self.assertEqual(inventory["genes"][0]["gene"], "GENE1")
        self.assertEqual(inventory["genes"][0]["total"], 3)
        self.assertEqual(
            inventory["genes"][0]["phenotypes"],
            {"breast cancer": 1},
        )
        self.assertEqual(
            inventory["genes"][0]["general_phenotypes"],
            {"type 2 diabetes": 1},
        )

    def test_fallback_status_is_global_and_uses_a_live_expiry(self):
        html = (ROOT / "static" / "admin-documents.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "admin-documents.js").read_text(encoding="utf-8")
        styles = (ROOT / "static" / "admin-documents.css").read_text(encoding="utf-8")

        self.assertIn("Semantic Scholar cooldown", html)
        self.assertIn("cooldown_expires_at", script)
        self.assertIn("Applies to all Semantic Scholar fallback requests", script)
        self.assertIn("Last query:", script)
        self.assertIn('deferred: "Skipped — cooldown active"', script)
        self.assertNotIn("titleCase(item.phenotype)", script)
        self.assertIn("transform: translateY(-50%) rotate(45deg)", styles)
        self.assertIn("transform: translateY(-50%) rotate(225deg)", styles)
        self.assertNotIn('content: "⌄"', styles)

    def test_browse_is_gene_scoped_and_sorts_by_citations(self):
        result = self.rag.browse_documents(gene="GENE1")
        self.assertEqual(result["total"], 3)
        self.assertEqual(
            [row["id"] for row in result["documents"]],
            ["s2::phenotype::GENE1::b", "s2::general::GENE1::a", "ot::GENE1"],
        )
        self.assertNotIn("embedding", result["documents"][0])

    def test_pool_search_and_pagination_are_applied_before_response(self):
        phenotype = self.rag.browse_documents(
            gene="GENE1",
            pool="phenotype",
            search="breast",
            limit=1,
        )
        self.assertEqual(phenotype["total"], 1)
        self.assertEqual(phenotype["documents"][0]["paper_id"], "b")

        selected_phenotype = self.rag.browse_documents(
            gene="GENE1",
            phenotype="breast cancer",
        )
        self.assertEqual(selected_phenotype["total"], 1)
        self.assertEqual(selected_phenotype["documents"][0]["pool"], "phenotype")

        second = self.rag.browse_documents(
            gene="GENE1",
            sort="title",
            offset=1,
            limit=1,
        )
        self.assertEqual(second["total"], 3)
        self.assertEqual(len(second["documents"]), 1)

    def test_source_filter_is_applied_before_pagination(self):
        semantic_scholar = self.rag.browse_documents(
            gene="GENE1",
            source="semanticscholar",
            limit=1,
        )
        self.assertEqual(semantic_scholar["source"], "semanticscholar")
        self.assertEqual(semantic_scholar["total"], 1)
        self.assertEqual(len(semantic_scholar["documents"]), 1)
        self.assertTrue(
            all(row["source"] == "semanticscholar" for row in semantic_scholar["documents"])
        )

        europe_pmc = self.rag.browse_documents(
            gene="GENE1",
            source="europe_pmc",
        )
        self.assertEqual(europe_pmc["total"], 1)
        self.assertEqual(europe_pmc["documents"][0]["source"], "europe_pmc")

    def test_one_exact_document_can_be_deleted_without_touching_other_records(self):
        deleted = self.rag.delete_document_by_id("s2::phenotype::GENE1::b")

        self.assertEqual(deleted["gene"], "GENE1")
        self.assertEqual(deleted["source"], "semanticscholar")
        remaining = self.rag.browse_documents(gene="GENE1")
        self.assertEqual(remaining["total"], 2)
        self.assertNotIn(
            "s2::phenotype::GENE1::b",
            [row["id"] for row in remaining["documents"]],
        )
        self.assertEqual(len(self.rag._collection.rows), 3)

    def test_deleting_an_unknown_document_is_a_noop(self):
        self.assertIsNone(self.rag.delete_document_by_id("missing"))
        self.assertEqual(len(self.rag._collection.rows), 4)


if __name__ == "__main__":
    unittest.main()
