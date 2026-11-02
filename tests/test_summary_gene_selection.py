from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd
from pydantic import ValidationError
from starlette.requests import Request

from agents.explanation import ExplanationAgent
from routes.summary import summary_preview
from schemas import SummaryRequest
from tests.support import ContractTestCase, ROOT


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

    def get_bottom_genes(self, pid=None, bottom_n=None, **_kwargs):
        count = bottom_n or self.default_top_n
        return pd.DataFrame({
            "Gene": [f"LOW_{index}" for index in range(1, count + 1)],
            "contribution": [-float(index) for index in range(1, count + 1)],
        })


class FakeExplanationAgent:
    def __init__(self):
        self.gene_agent = FakeGeneAgent()


class SummaryGeneSelectionTests(ContractTestCase):
    @staticmethod
    def request():
        return Request({"type": "http", "headers": []})

    def test_summary_request_defaults_to_five_genes_per_section(self):
        request = SummaryRequest(individual_id="HG00001")
        self.assertEqual(request.gene_count, 5)

    def test_summary_request_rejects_counts_outside_one_to_five(self):
        for invalid_count in (0, 6):
            with self.subTest(gene_count=invalid_count):
                with self.assertRaises(ValidationError):
                    SummaryRequest(individual_id="HG00001", gene_count=invalid_count)

    def test_target_genes_include_both_contribution_directions(self):
        agent = ExplanationAgent.__new__(ExplanationAgent)
        agent.gene_agent = FakeGeneAgent()

        self.assertEqual(
            agent.get_target_genes("HG00001"),
            ["GENE_A", "GENE_B", "GENE_C", "GENE_D", "GENE_E", "LOW_1", "LOW_2", "LOW_3", "LOW_4", "LOW_5"],
        )
        self.assertEqual(
            agent.get_target_genes("HG00001", gene_count=2),
            ["GENE_A", "GENE_B", "LOW_1", "LOW_2"],
        )

    def test_simple_summary_restores_compact_top_and_bottom_five_rankings(self):
        agent = ExplanationAgent.__new__(ExplanationAgent)
        top_rows = [
            {
                "gene": f"TOP_{index}",
                "individual_contribution": 10.0 - index,
                "population_rank": index,
            }
            for index in range(1, 7)
        ]
        bottom_rows = [
            {
                "gene": f"BOTTOM_{index}",
                "individual_contribution": -10.0 + index,
                "population_rank": index,
            }
            for index in range(1, 7)
        ]

        summary, payload = agent._build_simple_summary(
            pid="HG00001",
            density_profile={"percentile": 75.0, "prs_value": 1.25},
            top_rows=top_rows,
            bottom_rows=bottom_rows,
            gene_sections=[],
            language="en",
            plain_language_interpretation=(
                "The strongest contributions cluster around insulin-producing cell function [1,3].\n\n"
                "These model contributions do not prove that the selected genes cause disease [6]."
            ),
        )

        self.assertIn("Plain-Language Interpretation", summary)
        self.assertIn("insulin-producing cell function [1,3]", summary)
        self.assertIn("do not prove", summary)
        self.assertLess(summary.index("Risk Overview"), summary.index("Plain-Language Interpretation"))
        self.assertLess(summary.index("Plain-Language Interpretation"), summary.index("Top 5 (risk-increasing)"))
        self.assertIn("insulin-producing cell function", payload["plain_language_interpretation"])
        self.assertIn("Top 5 (risk-increasing)", summary)
        self.assertIn("Bottom 5 (risk-lowering)", summary)
        self.assertIn("TOP_5", summary)
        self.assertIn("BOTTOM_5", summary)
        self.assertNotIn("TOP_6", summary)
        self.assertNotIn("BOTTOM_6", summary)
        self.assertEqual(len(payload["gene_rankings"]["top"]), 5)
        self.assertEqual(len(payload["gene_rankings"]["bottom"]), 5)

    def test_preview_returns_the_same_top_gene_count(self):
        request = SummaryRequest(individual_id="HG00001", gene_count=3)
        with patch("routes.summary.get_expl_agent", return_value=FakeExplanationAgent()):
            result = summary_preview(request, self.request())

        self.assertEqual(
            result["genes"],
            ["GENE_A", "GENE_B", "GENE_C", "LOW_1", "LOW_2", "LOW_3"],
        )
        self.assertEqual(result["gene_count"], 6)

    def test_dashboard_gene_selection_controls(self):
        self.run_contract_checks((
            "_check_dashboard_uses_a_bounded_slider_with_five_gene_default",
            "_check_slider_updates_the_existing_gene_count_pipeline",
            "_check_chat_composer_controls_share_height_and_alignment",
            "_check_slider_labels_account_for_thumb_center",
        ))

    def _check_dashboard_uses_a_bounded_slider_with_five_gene_default(self):
        html = (ROOT / "static" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('type="range"', html)
        self.assertIn('id="summary-gene-count"', html)
        self.assertIn('min="1"', html)
        self.assertIn('max="5"', html)
        self.assertIn('step="1"', html)
        self.assertIn('value="5"', html)
        self.assertNotIn("data-gene-count", html)
        self.assertNotIn('id="gene-count-value"', html)

    def _check_slider_updates_the_existing_gene_count_pipeline(self):
        javascript = (ROOT / "static" / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn('summaryGeneCount.addEventListener("input"', javascript)
        self.assertIn("setSummaryGeneCount(summaryGeneCount.value", javascript)

    def _check_chat_composer_controls_share_height_and_alignment(self):
        css = (ROOT / "static" / "dashboard.css").read_text(encoding="utf-8")

        self.assertIn("--composer-control-height: 46px", css)
        self.assertIn("height: var(--composer-control-height)", css)
        self.assertIn("margin: 0;", css)
        self.assertIn("line-height: 1;", css)

    def _check_slider_labels_account_for_thumb_center(self):
        css = (ROOT / "static" / "dashboard.css").read_text(encoding="utf-8")

        self.assertIn("--slider-thumb-size: 1.25rem", css)
        self.assertIn("left: calc(var(--slider-thumb-size) / 2)", css)
        self.assertIn("left: calc(25% + var(--slider-thumb-size) / 4)", css)
        self.assertIn("left: calc(75% - var(--slider-thumb-size) / 4)", css)
        self.assertIn("left: calc(100% - var(--slider-thumb-size) / 2)", css)
        self.assertIn(".gene-count-scale > span", css)


if __name__ == "__main__":
    unittest.main()
