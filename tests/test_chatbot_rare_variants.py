from __future__ import annotations

import unittest
from unittest.mock import Mock

import pandas as pd

from agents.conversation import ConversationAgent
from agents.explanation import ExplanationAgent

# Made-up findings; the exact-variant fields must never reach the model.
EXACT_VARIANT = "NC_000013.11:g.99999999del"
RSID = "rs99999999"
FINDINGS = {
    "active_disease_group": {
        "disease_label": "Breast Cancer",
        "findings": [{
            "gene": "BRCA2", "moi_call": "alert", "consequence": "frameshift", "clnsig": "P", "stars": 2,
            "clinvar_conditions": "Hereditary breast ovarian cancer syndrome",
            "hgvs": EXACT_VARIANT, "rsid": RSID, "genotype": "0/1",
            "actionability": [{
                "doc_id": "AC133", "context": "Adult", "condition": "Hereditary Breast and Ovarian Cancer",
                "interventions": ["Surveillance"], "url": "https://actionability.clinicalgenome.org/ac/Adult/ui/stg2SummaryRpt?doc=AC133",
            }],
        }],
    },
    "other_disease_groups": [{
        "disease_label": "Coronary Artery Disease",
        "findings": [{"gene": "LDLR", "moi_call": "alert", "consequence": "missense", "clnsig": "LP", "stars": 1}],
    }],
    "unassigned_group": {
        "findings": [{"gene": "GJB2", "moi_call": "carrier", "consequence": "nonsense", "clnsig": "P", "stars": 3}],
    },
}
NO_FINDINGS = {"active_disease_group": {"findings": []}, "other_disease_groups": [], "unassigned_group": {"findings": []}}


class FakeGeneAgent:
    default_top_n = 5

    def get_top_genes(self, _pid, top_n=5):
        return pd.DataFrame({"Gene": ["GENE1", "GENE2", "GENE3", "GENE4", "GENE5"][:top_n]}), pd.DataFrame()

    def get_bottom_genes(self, _pid, bottom_n=5):
        return pd.DataFrame({"Gene": ["LOW1", "LOW2", "LOW3", "LOW4", "LOW5"][:bottom_n]})


class FakeEvidenceAgent:
    def retrieve_gene_context_for_question(self, gene, *_args, **_kwargs):
        return [f"{gene} has published evidence."], [], "TEST"


class PromptCapturingLLM:
    model = "test/model"

    def __init__(self):
        self.prompts: list[str] = []

    def chat(self, messages, **_kwargs):
        self.prompts.append(messages[-1]["content"])
        return '{"answer":"Model answer."}'


def agent_with(provider):
    llm = PromptCapturingLLM()
    agent = ExplanationAgent(
        llm=llm,
        gene_agent=FakeGeneAgent(),
        evidence_agent=FakeEvidenceAgent(),
        ot_agent=None,
        conversation_agent=ConversationAgent(),
        primary_phenotype="breast cancer",
        disease_display_name="Breast Cancer",
        minimize_sensitive_context=True,
        rare_variant_panel_available=True,
        rare_findings_provider=provider,
    )
    agent.build_explanation = Mock(side_effect=AssertionError("follow-up rebuilt the summary"))
    return agent, llm


def ask(agent, question):
    return agent.answer_followup(
        "person-1",
        question,
        existing_references=[],
        summary_context={"Model Safe Context": "Saved summary.", "Gene Count Used": 5},
        conversation_state={"active_genes": ["GENE1"], "active_phenotypes": ["breast cancer"]},
    )


class ChatbotRareVariantTests(unittest.TestCase):
    def test_model_gets_gene_level_findings_and_reader_gets_the_exact_variants(self):
        agent, llm = agent_with(lambda _pid: FINDINGS)
        result = ask(agent, "Does this patient carry a pathogenic variant relevant to breast cancer?")

        prompt = llm.prompts[-1]
        self.assertIn("Rare-variant findings:", prompt)
        self.assertIn("BRCA2: panel alert; frameshift; ClinVar pathogenic, ClinVar review 2 stars", prompt)
        self.assertIn("LDLR", prompt)
        self.assertIn("linked to the Coronary Artery Disease panel", prompt)
        self.assertIn("GJB2: carrier", prompt)
        for private in (EXACT_VARIANT, RSID, "0/1"):
            self.assertNotIn(private, prompt)
        self.assertNotIn("are not available to you", prompt)

        answer = result["Generated Answer"]
        self.assertIn(EXACT_VARIANT, answer)      # server-rendered table
        self.assertIn("Model answer.", answer)

    def test_actionability_reports_are_references_not_recommendations(self):
        agent, llm = agent_with(lambda _pid: FINDINGS)
        result = ask(agent, "Does this patient carry a pathogenic variant relevant to breast cancer?")

        prompt = llm.prompts[-1]
        self.assertIn("ClinGen Actionability report AC133: Hereditary Breast and Ovarian Cancer", prompt)
        self.assertIn("interventions covered: Surveillance", prompt)
        self.assertIn("Never recommend, suggest or imply any of those interventions for this individual", prompt)
        answer = result["Generated Answer"]
        self.assertIn("ClinGen Actionability reports (references, not recommendations for this individual)", answer)
        self.assertIn("(https://actionability.clinicalgenome.org/ac/Adult/ui/stg2SummaryRpt?doc=AC133)", answer)

    def test_no_recorded_finding_is_worded_as_not_recorded(self):
        agent, llm = agent_with(lambda _pid: NO_FINDINGS)
        result = ask(agent, "Is there a rare variant for this patient?")

        self.assertIn("- none recorded", llm.prompts[-1])
        self.assertIn("never say the individual has no pathogenic variants", llm.prompts[-1])
        self.assertIn("No rare-variant finding is recorded for this individual.", result["Generated Answer"])

    def test_other_patient_questions_get_findings_without_the_table(self):
        agent, llm = agent_with(lambda _pid: FINDINGS)
        result = ask(agent, "How should I read this patient's breast cancer result?")

        self.assertIn("BRCA2: panel alert", llm.prompts[-1])
        self.assertNotIn("directly above your answer; do not repeat that table", llm.prompts[-1])
        self.assertNotIn(EXACT_VARIANT, result["Generated Answer"])

    def test_variant_on_two_panels_is_listed_once_with_both_panels(self):
        # The data hold one row per panel assignment: the same BRCA2 variant on
        # the breast and pancreatic cancer panels arrives twice.
        brca2 = FINDINGS["active_disease_group"]["findings"][0]
        duplicated = {
            **FINDINGS,
            "other_disease_groups": FINDINGS["other_disease_groups"] + [{
                "disease_label": "Pancreatic Cancer",
                "findings": [{**brca2, "variant": "13:99999999:CT:C"}],
            }],
            "active_disease_group": {
                "disease_label": "Breast Cancer",
                "findings": [{**brca2, "variant": "13:99999999:CT:C"}],
            },
        }
        agent, llm = agent_with(lambda _pid: duplicated)
        result = ask(agent, "Does this patient carry a pathogenic variant?")

        prompt = llm.prompts[-1]
        self.assertEqual(prompt.count("BRCA2: panel alert"), 1)
        self.assertIn("also linked to the Pancreatic Cancer panel", prompt)
        answer = result["Generated Answer"]
        self.assertEqual(answer.count(EXACT_VARIANT), 1)
        self.assertIn("Also on panel", answer)
        self.assertIn("Pancreatic Cancer", answer)

    def test_without_findings_the_chat_still_refuses_to_guess(self):
        agent, llm = agent_with(None)
        ask(agent, "Does this patient carry a pathogenic variant?")

        self.assertIn("are not available to you", llm.prompts[-1])
        self.assertNotIn("Rare-variant findings:", llm.prompts[-1])


if __name__ == "__main__":
    unittest.main()
