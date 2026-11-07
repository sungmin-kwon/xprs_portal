import unittest

from agents.explanation import ExplanationAgent
from reference_utils import normalize_citations


class ReferenceNormalizationTests(unittest.TestCase):
    def test_expands_citation_ranges_and_grouped_styles_before_remapping(self):
        normalized = normalize_citations(
            "Ranges [1-3, 5], full width ［6–7］, and CJK 【8，9】."
        )

        self.assertEqual(
            normalized,
            "Ranges [1][2][3][5], full width [6][7], and CJK [8][9].",
        )

        remapped = ExplanationAgent._remap_citations(
            "Evidence [1-3, 5]; stale [8].",
            {1: 11, 2: 12, 3: 13, 5: 15},
        )
        self.assertEqual(remapped, "Evidence [11][12][13][15]; stale .")

    def test_reference_normalization_expands_ranges_without_caller_preprocessing(self):
        references = {
            number: {
                "paperId": f"PMID:{number}",
                "pmid": str(number),
                "title": f"Paper {number}",
                "gene": "GENE1",
                "source": "europe_pmc",
            }
            for number in (1, 2, 3)
        }
        chunks = {number: f"Abstract {number}" for number in references}

        body, compact, output, mapping = ExplanationAgent._normalize_used_references(
            "Supported by a range [1-3].",
            references,
            chunks,
        )

        self.assertEqual(body, "Supported by a range [1][2][3].")
        self.assertEqual(mapping, {1: 1, 2: 2, 3: 3})
        self.assertEqual([item["n"] for item in output], [1, 2, 3])
        self.assertEqual(
            compact,
            "[1] Abstract 1\n[2] Abstract 2\n[3] Abstract 3",
        )

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
