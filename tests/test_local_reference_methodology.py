from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock

import pandas as pd

from agents.conversation import ConversationAgent
from agents.explanation import ExplanationAgent
from agents.local_reference import LocalReferenceAgent


ROOT = Path(__file__).resolve().parents[1]


class FakeGeneAgent:
    default_top_n = 5

    def get_top_genes(self, _pid, top_n=5):
        return pd.DataFrame({"Gene": ["GENE1", "GENE2"][:top_n]}), pd.DataFrame()

    def get_bottom_genes(self, _pid, bottom_n=5):
        return pd.DataFrame({"Gene": ["GENE3", "GENE4"][:bottom_n]})


class CapturingLLM:
    model = "test-model"

    def __init__(self):
        self.messages = []

    def chat(self, messages, timeout):
        self.messages = messages
        return '{"answer": "Detailed methodology answer."}'


class LocalReferenceMethodologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = LocalReferenceAgent(ROOT / "ref")

    def test_markdown_sections_preserve_short_equations(self):
        gene_section = next(
            entry
            for entry in self.agent._entries
            if entry["title"] == "XPRS Methods Note"
            and entry["heading"] == "Gene-Level Contribution"
        )

        self.assertIn("CS_{\\mathrm{gene},j}", gene_section["text"])
        self.assertIn("G_{0,i} = G_i - p_i", gene_section["text"])

    def test_xprs_calculation_query_receives_complete_method_sections(self):
        hits = self.agent.query_methodology("How is XPRS calculated?")
        headings = [hit["heading"] for hit in hits]
        context = "\n".join(hit["text"] for hit in hits)

        self.assertIn("Inputs", headings)
        self.assertIn("Step 1: Preprocessing and Variant Mapping", headings)
        self.assertIn("Gene-Level Contribution", headings)
        self.assertIn("Population Rank", headings)
        self.assertIn("SNP-Level Contribution", headings)
        self.assertIn("CS_{\\mathrm{gene},j}", context)
        self.assertIn("A_{\\mathrm{gene},j}", context)
        self.assertIn("CS_{\\mathrm{SNP},i}", context)
        self.assertTrue(all(hit["title"] == "XPRS Methods Note" for hit in hits))

    def test_prs_construction_query_uses_prs_reference(self):
        hits = self.agent.query_methodology("How is a PRS constructed?")

        self.assertTrue(hits)
        self.assertEqual(hits[0]["heading"], "What a PRS Is")
        self.assertTrue(
            all(
                hit["title"] == "Polygenic Risk Score Clinical Relevance Note"
                for hit in hits
            )
        )

    def test_followup_methodology_fast_path_skips_gene_rag_and_includes_formulas(self):
        llm = CapturingLLM()
        query_agent = Mock()
        evidence_agent = Mock()
        explanation = ExplanationAgent(
            llm=llm,
            gene_agent=FakeGeneAgent(),
            evidence_agent=evidence_agent,
            ot_agent=Mock(),
            query_agent=query_agent,
            conversation_agent=ConversationAgent(),
        )
        explanation.build_explanation = Mock(
            side_effect=AssertionError("methodology path rebuilt the gene summary")
        )

        result = explanation.answer_followup("DEMO001", "How is XPRS calculated?")

        self.assertEqual(result["Generated Answer"], "Detailed methodology answer.")
        self.assertEqual(result["Discussed Genes"], [])
        query_agent.analyze.assert_not_called()
        evidence_agent.retrieve_gene_context_for_question.assert_not_called()
        explanation.build_explanation.assert_not_called()
        prompt = llm.messages[-1]["content"]
        self.assertIn("CS_{\\mathrm{gene},j}", prompt)
        self.assertIn("A_{\\mathrm{gene},j}", prompt)
        self.assertIn("CS_{\\mathrm{SNP},i}", prompt)
        self.assertIn("important limitations", prompt)

    def test_dashboard_repairs_escaped_xprs_subscripts(self):
        script = (ROOT / "static" / "dashboard.js").read_text(encoding="utf-8")

        self.assertIn('"CS_{\\\\mathrm{gene},j}"', script)
        self.assertIn('"A_{\\\\mathrm{gene},j}"', script)
        self.assertIn('"CS_{\\\\mathrm{SNP},i}"', script)


if __name__ == "__main__":
    unittest.main()
