from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from llm_utils import LLMAgent, sanitize_kpredict_text
from agents.explanation import ExplanationAgent


class RecordingCompletions:
    def __init__(self):
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )


class OpenRouterPrivacyTests(unittest.TestCase):
    def test_every_openrouter_completion_enforces_zdr_and_denies_collection(self):
        completions = RecordingCompletions()
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        agent = LLMAgent(provider="openrouter", client=client, model="test/model")

        self.assertEqual(agent.chat([{"role": "user", "content": "hello"}]), "ok")
        request = completions.requests[0]
        self.assertEqual(
            request["extra_body"],
            {"provider": {"zdr": True, "data_collection": "deny"}},
        )

    def test_kpredict_mode_removes_direct_identifiers_and_variant_tokens(self):
        completions = RecordingCompletions()
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        agent = LLMAgent(
            provider="openrouter",
            client=client,
            model="test/model",
            privacy_mode="kpredict",
        )
        sensitive = (
            "KP-ABCDEF123456 rs123456 NC_000012.12:g.120994283G>A "
            "chr12:120994283 with genotype 0/1 PRS: 106.746, 96.5th percentile, "
            "contribution score=-2.5, sex: F"
        )

        agent.chat([{"role": "user", "content": sensitive}])
        sent = completions.requests[0]["messages"][0]["content"]
        self.assertNotIn("KP-ABCDEF123456", sent)
        self.assertNotIn("rs123456", sent)
        self.assertNotIn("NC_000012.12:g.120994283G>A", sent)
        self.assertNotIn("chr12:120994283", sent)
        self.assertNotIn("0/1", sent)
        self.assertNotIn("106.746", sent)
        self.assertNotIn("96.5th percentile", sent)
        self.assertNotIn("-2.5", sent)
        self.assertNotIn("sex: F", sent)

    def test_openrouter_calls_fail_closed_if_zdr_enforcement_is_disabled(self):
        completions = RecordingCompletions()
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        agent = LLMAgent(provider="openrouter", client=client, model="test/model")

        with patch("llm_utils.OPENROUTER_ZDR_REQUIRED", False):
            with self.assertRaisesRegex(RuntimeError, "ZDR enforcement is disabled"):
                agent.chat([{"role": "user", "content": "hello"}])
        self.assertEqual(completions.requests, [])

    def test_sanitizer_does_not_change_ordinary_biomedical_context(self):
        value = "ESR1 and TOX3 are discussed in breast cancer literature."
        self.assertEqual(sanitize_kpredict_text(value), value)

    def test_disease_aware_prompts_use_minimized_kpredict_context(self):
        class PromptRecorder:
            model = "test/model"

            def __init__(self):
                self.prompts = []

            def chat(self, messages, **_kwargs):
                prompt = messages[-1]["content"]
                self.prompts.append(prompt)
                if "one key: intro" in prompt:
                    return '{"intro":"ok"}'
                if "integrated_view" in prompt:
                    return '{"integrated_view":"ok"}'
                if "one key: answer" in prompt:
                    return '{"answer":"ok"}'
                return '{"why_it_matters":"ok","disease_relevance":"ok","clinical_meaning":"ok"}'

        llm = PromptRecorder()
        agent = ExplanationAgent(
            llm=llm,
            gene_agent=None,
            evidence_agent=None,
            ot_agent=None,
            primary_phenotype="gastric cancer",
            disease_display_name="Gastric Cancer",
            minimize_sensitive_context=True,
        )
        ranking = agent._model_ranking_text(["GENE1", "GENE2"], "en")
        agent._generate_intro(
            gene_count=2,
            selected_genes="GENE1, GENE2",
            top_genes_summary=ranking,
            language="en",
        )
        agent._generate_gene_section(
            gene="GENE1",
            individual_contribution="selected top-contributor rank only; exact value withheld",
            evidence_context="public evidence",
            citation_rules="none",
            language="en",
        )
        agent._generate_integrated_view(
            selected_genes="GENE1, GENE2",
            top_genes_summary=ranking,
            gene_takeaways="public evidence",
            citation_rules="none",
            language="en",
        )
        agent._generate_followup_text(
            background="public evidence",
            compact_ctx="public evidence",
            ref_index="none",
            question="What does this mean?",
            n_max=0,
        )

        self.assertTrue(all("Gastric Cancer" in prompt for prompt in llm.prompts))
        combined = "\n".join(llm.prompts)
        self.assertNotIn("KP-ABCDEF123456", combined)
        self.assertNotIn("1.23456", combined)
        self.assertIn("exact value withheld", combined)


if __name__ == "__main__":
    unittest.main()
