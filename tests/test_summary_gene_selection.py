from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd
from pydantic import ValidationError

from agents.explanation import ExplanationAgent
from routes.summary import summary_preview
from schemas import SummaryRequest


class FakeGeneAgent:
    default_top_n = 5

    def __init__(self):
        self.genes = ["GENE_A", "GENE_B", "GENE_C", "GENE_D", "GENE_E"]

    def get_top_genes(self, pid=None, top_n=None, **_kwargs):
        count = top_n or self.default_top_n
        top = pd.DataFrame({
            "Gene": self.genes[:count],
            "contribution": list(range(count, 0, -1)),
        })
        return top, pd.DataFrame()


class FakeExplanationAgent:
    def __init__(self):
        self.gene_agent = FakeGeneAgent()


class SummaryGeneSelectionTests(unittest.TestCase):
    def test_summary_request_defaults_to_two_genes(self):
        request = SummaryRequest(individual_id="HG00001")
        self.assertEqual(request.gene_count, 2)

    def test_summary_request_rejects_counts_outside_one_to_five(self):
        for invalid_count in (0, 6):
            with self.subTest(gene_count=invalid_count):
                with self.assertRaises(ValidationError):
                    SummaryRequest(individual_id="HG00001", gene_count=invalid_count)

    def test_target_genes_are_the_requested_top_contributors(self):
        agent = ExplanationAgent.__new__(ExplanationAgent)
        agent.gene_agent = FakeGeneAgent()

        self.assertEqual(agent.get_target_genes("HG00001"), ["GENE_A", "GENE_B"])
        self.assertEqual(
            agent.get_target_genes("HG00001", gene_count=4),
            ["GENE_A", "GENE_B", "GENE_C", "GENE_D"],
        )

    def test_preview_returns_the_same_top_gene_count(self):
        request = SummaryRequest(individual_id="HG00001", gene_count=3)
        with patch("routes.summary.get_expl_agent", return_value=FakeExplanationAgent()):
            result = summary_preview(request)

        self.assertEqual(result["genes"], ["GENE_A", "GENE_B", "GENE_C"])
        self.assertEqual(result["gene_count"], 3)


if __name__ == "__main__":
    unittest.main()
