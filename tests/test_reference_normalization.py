import unittest

from agents.explanation import ExplanationAgent


class ReferenceNormalizationTests(unittest.TestCase):
    def test_deduplicates_references_merges_genes_and_removes_ghost_citations(self):
        answer = "Second [2]. First [1]. Unsupported [99].\n\n## References\nDo not keep this."
        references = {
            1: {
                "paperId": "PMID:123",
                "pmid": "123",
                "title": "Shared paper",
                "gene": "GENE1",
                "source": "europe_pmc",
            },
            2: {
                "paperId": "PMID:123",
                "pmid": "123",
                "title": "Shared paper",
                "gene": "GENE2",
                "source": "europe_pmc",
            },
        }
        chunks = {1: "First abstract", 2: "Second abstract"}

        body, compact, output, mapping = ExplanationAgent._normalize_used_references(
            answer,
            references,
            chunks,
        )

        self.assertEqual(mapping, {2: 1, 1: 1})
        self.assertEqual(body, "Second [1]. First [1]. Unsupported .")
        self.assertNotIn("References", body)
        self.assertEqual(compact, "[1] Second abstract\n[1] First abstract")
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["gene"], "GENE2, GENE1")
        self.assertEqual(output[0]["paperId"], "PMID:123")

    def test_omits_uncited_records(self):
        body, compact, output, mapping = ExplanationAgent._normalize_used_references(
            "No citations were used.",
            {1: {"paperId": "PMID:1", "title": "Unused"}},
            {1: "Unused abstract"},
        )

        self.assertEqual(body, "No citations were used.")
        self.assertEqual(compact, "")
        self.assertEqual(output, [])
        self.assertEqual(mapping, {})


if __name__ == "__main__":
    unittest.main()
