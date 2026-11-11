from __future__ import annotations

import unittest
from unittest.mock import Mock

import pandas as pd

from agents.conversation import ConversationAgent
from agents.explanation import ExplanationAgent
from agents.local_reference import LocalReferenceAgent
from tests.support import ROOT


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


class NoEvidenceAgent:
    def retrieve_gene_context_for_question(self, *_args, **_kwargs):
        return [], [], "RAG"


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

    def _explanation_agent(self, llm):
        explanation = ExplanationAgent(
            llm=llm,
            gene_agent=FakeGeneAgent(),
            evidence_agent=NoEvidenceAgent(),
            ot_agent=Mock(),
            query_agent=Mock(**{
                "analyze.return_value": {
                    "rewritten_query": "Does this individual's PRS exceed a guideline threshold?",
                    "genes": [],
                    "phenotypes": [],
                    "scope": "general",
                    "disease_intent": "disease_neutral",
                },
            }),
            conversation_agent=ConversationAgent(),
            minimize_sensitive_context=True,
        )
        explanation.build_explanation = Mock(
            side_effect=AssertionError("follow-up rebuilt the gene summary")
        )
        return explanation

    def test_patient_specific_detector_matches_clinician_phrasing(self):
        # Phrasings from the clinician question bank (2026-11-10).
        patient_questions = [
            "What does this patient's percentile and standardized PRS for breast cancer mean?",
            "Does this patient exceed a guideline threshold (e.g. 20% lifetime breast cancer risk)?",
            "Summarise this report in three lines.",
            "Please explain this report in Korean.",
            "이 환자의 PRS 결과를 설명해 주세요.",
            "Repeat my PRS percentile.",
        ]
        general_questions = [
            "How is XPRS calculated?",
            "How accurate is the breast cancer PRS? (C-index, HR per SD)",
            "What does BRCA1 do?",
        ]
        for question in patient_questions:
            with self.subTest(question=question):
                self.assertTrue(ExplanationAgent._is_patient_specific_question(question))
        for question in general_questions:
            with self.subTest(question=question):
                self.assertFalse(ExplanationAgent._is_patient_specific_question(question))

    def test_this_patient_percentile_question_uses_local_answer(self):
        self.assertTrue(ExplanationAgent._is_personal_prs_position_question(
            "What does this patient's percentile and standardized PRS for breast cancer mean?"
        ))

    def test_patient_specific_prs_question_keeps_report_context(self):
        llm = CapturingLLM()
        explanation = self._explanation_agent(llm)

        result = explanation.answer_followup(
            "KP-ABCDEF123456",
            "Does this patient's PRS exceed a guideline threshold?",
            summary_context={"Model Safe Context": "Saved report gene-evidence summary."},
        )

        self.assertTrue(result["Store In History"])
        prompt = llm.messages[-1]["content"]
        self.assertIn("Saved report gene-evidence summary.", prompt)
        self.assertIn("about the individual's XPRS report", prompt)
        self.assertNotIn("(1) what is being calculated", prompt)

    def test_general_prs_question_skips_calculation_walkthrough(self):
        llm = CapturingLLM()
        explanation = self._explanation_agent(llm)

        explanation.answer_followup("DEMO001", "How accurate is the PRS?")

        prompt = llm.messages[-1]["content"]
        self.assertIn("general PRS/XPRS question", prompt)
        self.assertNotIn("(1) what is being calculated", prompt)

    def test_every_section_carries_its_source_citation(self):
        prs_hits = self.agent.query_methodology("How is a PRS constructed?")
        xprs_hits = self.agent.query_methodology("How is XPRS calculated?")

        self.assertTrue(prs_hits and xprs_hits)
        for hit in prs_hits:
            self.assertIn("type 2 diabetes", hit["source_citation"])
        for hit in xprs_hits:
            self.assertIn("XPRS: a tool for interpretable", hit["source_citation"])

    def test_followup_prompt_labels_source_study_and_hides_prompt_internals(self):
        llm = CapturingLLM()
        explanation = self._explanation_agent(llm)
        explanation.disease_display_name = "Breast Cancer"

        explanation.answer_followup("DEMO001", "How is a PRS constructed?")

        prompt = llm.messages[-1]["content"]
        self.assertIn("Source study: Kim NY", prompt)
        self.assertIn("The model behind this report is the Breast Cancer XPRS model", prompt)
        self.assertIn("Never mention internal inputs such as 'the background'", prompt)

    REPORT_CONTEXT = {
        "Model Safe Context": "Saved report gene-evidence summary.",
        "Report Payload": {
            # Same shape as the full report payload stored in the chat session.
            "risk_overview": {"percentile": 99.84},
            "top_genes": {
                "rows": [{"gene": "ESR1", "individual_contribution": 0.1234, "population_rank": 1}],
            },
            "bottom_genes": {
                "rows": [{
                    "gene": "Unannotated region chr12 115.19–115.59 Mb",
                    "individual_contribution": -0.04493,
                    "population_rank": 45,
                }],
            },
        },
    }

    def test_gene_question_shows_report_values_without_sending_them(self):
        llm = CapturingLLM()
        explanation = self._explanation_agent(llm)

        result = explanation.answer_followup(
            "KP-ABCDEF123456",
            "Which genes matter most for this patient, and how much do they contribute?",
            summary_context=self.REPORT_CONTEXT,
            language="en",
        )

        answer = result["Generated Answer"]
        self.assertTrue(answer.startswith("**From this report:**"))
        self.assertIn("higher than about 99.8% of the reference cohort", answer)
        self.assertIn("| ESR1 | 0.123 | 1 |", answer)
        self.assertIn("| Unannotated region chr12 115.19–115.59 Mb | -0.0449 | 45 |", answer)
        self.assertTrue(answer.endswith("Detailed methodology answer."))

        prompt = llm.messages[-1]["content"]
        self.assertIn("directly above your answer", prompt)
        for private_value in ("99.8", "0.123", "-0.0449"):
            self.assertNotIn(private_value, prompt)

    def test_non_gene_report_question_shows_percentile_only(self):
        llm = CapturingLLM()
        explanation = self._explanation_agent(llm)

        result = explanation.answer_followup(
            "KP-ABCDEF123456",
            "Summarise this report in three lines.",
            summary_context=self.REPORT_CONTEXT,
            language="en",
        )

        self.assertIn("99.8%", result["Generated Answer"])
        self.assertNotIn("| ESR1 |", result["Generated Answer"])

    def test_general_question_gets_no_report_values(self):
        llm = CapturingLLM()
        explanation = self._explanation_agent(llm)

        result = explanation.answer_followup(
            "KP-ABCDEF123456",
            "How accurate is the PRS?",
            summary_context=self.REPORT_CONTEXT,
            language="en",
        )

        self.assertNotIn("From this report", result["Generated Answer"])

    def test_rare_variant_detector_covers_question_bank(self):
        rare_questions = [
            "Is there a rare variant relevant to breast cancer in this patient?",  # D15
            "Does the top gene in the Important genes table carry a mutation that causes breast cancer?",  # D11
            "What do 'alert' and 'carrier' mean in this report?",  # T01
            "Is this variant really rare in East Asians?",  # T06
            "Could this be clonal haematopoiesis rather than a germline variant?",  # T07
            "The same variant appears under several diseases. Are these separate findings?",  # T08
            "There are no alerts. Can I reassure the patient?",  # T09
            "Which ClinVar and PanelApp versions were used?",  # T13
            "Were variants re-classified with ACMG/AMP criteria, or is this ClinVar only?",  # T14
            "이 환자에게 병원성 희귀 변이가 있나요?",
        ]
        prs_questions = [
            "Which genes are most important for this patient's breast cancer risk?",
            "Summarise this report in three lines.",
            "why no BRCA gene appears in the gene list?",
            "How accurate is the breast cancer PRS?",
        ]
        for question in rare_questions:
            with self.subTest(question=question):
                self.assertTrue(ExplanationAgent._is_rare_variant_question(question))
        for question in prs_questions:
            with self.subTest(question=question):
                self.assertFalse(ExplanationAgent._is_rare_variant_question(question))

    def test_rare_variant_question_gets_note_and_no_presence_claims(self):
        llm = CapturingLLM()
        explanation = self._explanation_agent(llm)
        explanation.rare_variant_panel_available = True

        result = explanation.answer_followup(
            "KP-ABCDEF123456",
            "Is there a rare variant relevant to breast cancer in this patient?",
            summary_context=self.REPORT_CONTEXT,
            language="en",
        )

        answer = result["Generated Answer"]
        self.assertTrue(answer.startswith("**About rare variants:**"))
        self.assertIn("Rare Variant Analysis", answer)
        # The rare-variant note replaces the PRS facts; it is not a PRS question.
        self.assertNotIn("99.8%", answer)
        prompt = llm.messages[-1]["content"]
        self.assertIn("Never state or imply that this individual has, or does not have", prompt)

    def test_public_cohort_gets_instruction_but_no_panel_note(self):
        llm = CapturingLLM()
        explanation = self._explanation_agent(llm)  # rare_variant_panel_available defaults to False

        result = explanation.answer_followup(
            "HG00436",
            "Is there a rare variant relevant to breast cancer in this patient?",
            summary_context=self.REPORT_CONTEXT,
            language="en",
        )

        self.assertNotIn("Rare Variant Analysis", result["Generated Answer"])
        self.assertIn("Never state or imply", llm.messages[-1]["content"])

    def test_dashboard_repairs_escaped_xprs_subscripts(self):
        script = (ROOT / "static" / "dashboard.js").read_text(encoding="utf-8")

        self.assertIn('"CS_{\\\\mathrm{gene},j}"', script)
        self.assertIn('"A_{\\\\mathrm{gene},j}"', script)
        self.assertIn('"CS_{\\\\mathrm{SNP},i}"', script)

    def test_dashboard_protects_and_normalizes_model_generated_math(self):
        script = (ROOT / "static" / "dashboard.js").read_text(encoding="utf-8")

        self.assertIn("function normalizeLatexExpression", script)
        self.assertIn("function normalizeDelimitedMath", script)
        self.assertIn("function renderMarkdownWithProtectedMath", script)
        self.assertIn("XPRSMATHTOKEN", script)
        self.assertIn("normalizeLatexExpression(displayDollar)", script)
        self.assertIn('"G_{0,i}"', script)
        self.assertIn('"\\\\beta_{\\\\mathrm{std},i}"', script)
        self.assertIn('"\\\\sum_{i \\\\in j}"', script)
        self.assertIn('"A_{\\\\mathrm{gene},j}"', script)
        self.assertIn('"\\\\operatorname{mean}_{\\\\mathrm{population}}("', script)
        self.assertIn('trimmed.includes("$")', script)
        self.assertIn("const rendered = renderMarkdownWithProtectedMath(normalizedText);", script)

    def test_dashboard_serves_katex_locally_with_required_assets(self):
        html = (ROOT / "static" / "dashboard.html").read_text(encoding="utf-8")
        vendor = ROOT / "static" / "vendor" / "katex"

        self.assertIn('/static/vendor/katex/katex.min.css?v=0.16.11', html)
        self.assertIn('/static/vendor/katex/katex.min.js?v=0.16.11', html)
        self.assertIn('/static/vendor/katex/contrib/auto-render.min.js?v=0.16.11', html)
        self.assertNotIn("cdn.jsdelivr.net/npm/katex", html)
        self.assertTrue((vendor / "katex.min.css").is_file())
        self.assertTrue((vendor / "katex.min.js").is_file())
        self.assertTrue((vendor / "contrib" / "auto-render.min.js").is_file())
        self.assertTrue((vendor / "fonts" / "KaTeX_Main-Regular.woff2").is_file())
        self.assertTrue((vendor / "LICENSE").is_file())


if __name__ == "__main__":
    unittest.main()
