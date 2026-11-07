from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from llm_utils import LLMAgent, sanitize_kpredict_text
from agents.conversation import ConversationAgent, ConversationState
from agents.explanation import ExplanationAgent
from routes.chat import _latest_assistant_response


class RecordingCompletions:
    def __init__(self):
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )


class SequenceCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


class OpenRouterPrivacyTests(unittest.TestCase):
    def test_malformed_openrouter_completion_is_retried_once(self):
        completions = SequenceCompletions([
            SimpleNamespace(choices=None),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="recovered"))]),
        ])
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        agent = LLMAgent(provider="openrouter", client=client, model="test/model")

        self.assertEqual(agent.chat([{"role": "user", "content": "hello"}]), "recovered")
        self.assertEqual(len(completions.requests), 2)
        self.assertTrue(all(
            request["extra_body"]["provider"]["zdr"] is True
            for request in completions.requests
        ))

    def test_repeated_malformed_completion_has_a_clear_error(self):
        completions = SequenceCompletions([
            SimpleNamespace(choices=None),
            SimpleNamespace(choices=[]),
            SimpleNamespace(choices=None),
        ])
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        agent = LLMAgent(provider="openrouter", client=client, model="test/model")

        with self.assertRaisesRegex(RuntimeError, "completion response contained no choices"):
            agent.chat([{"role": "user", "content": "hello"}])

        self.assertEqual(len(completions.requests), 3)

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

    def test_translation_request_is_in_domain_and_preserves_context(self):
        class RejectingResolver:
            def chat(self, *_args, **_kwargs):
                return '{"turn_type":"off_domain_request"}'

        state = ConversationState(
            active_genes=["KCNQ1", "CDKAL1"],
            active_phenotypes=["type 2 diabetes"],
            active_intent="primary_disease_summary",
        )
        resolution = ConversationAgent(RejectingResolver()).resolve_turn(
            question="Can you translate this into Korean?",
            state=state,
            available_genes=["KCNQ1", "CDKAL1"],
        )

        self.assertEqual(resolution["turn_type"], "biomedical_followup")
        self.assertEqual(resolution["translation_target"], "ko")
        self.assertEqual(resolution["resolved_genes"], ["KCNQ1", "CDKAL1"])
        self.assertEqual(resolution["resolved_intent"], "primary_disease_summary")
        self.assertIsNone(ConversationAgent.translation_target("Explain KCNQ1 in Korean."))

    def test_private_summary_translation_masks_then_restores_values(self):
        class FakeGeneAgent:
            default_top_n = 5

            def get_top_genes(self, _pid, top_n=5):
                return pd.DataFrame({"Gene": ["KCNQ1", "CDKAL1"][:top_n]}), pd.DataFrame()

            def get_bottom_genes(self, _pid, bottom_n=5):
                return pd.DataFrame({"Gene": ["LOW1"][:bottom_n]})

        class TranslationLLM:
            model = "test/model"

            def __init__(self):
                self.sent = ""

            def chat(self, messages, **_kwargs):
                self.sent = messages[-1]["content"]
                return self.sent.replace("Risk Overview", "위험 개요")

        llm = TranslationLLM()
        agent = ExplanationAgent(
            llm=llm,
            gene_agent=FakeGeneAgent(),
            evidence_agent=None,
            ot_agent=None,
            conversation_agent=ConversationAgent(),
            primary_phenotype="type 2 diabetes",
            disease_display_name="Type 2 Diabetes",
            minimize_sensitive_context=True,
        )
        source = (
            "### Risk Overview\n"
            "Individual: KP-ABCDEF123456\n"
            "This PRS is higher than about 93.6% of the cohort.\n"
            "- **KCNQ1** (contribution 0.16): evidence [1]."
        )
        references = [{"n": 1, "title": "KCNQ1 study"}]

        result = agent.answer_followup(
            "KP-ABCDEF123456",
            "Can you translate this into Korean?",
            existing_references=references,
            conversation_state={
                "active_genes": ["KCNQ1", "CDKAL1"],
                "active_phenotypes": ["type 2 diabetes"],
                "active_intent": "primary_disease_summary",
            },
            prior_assistant_response=source,
            language="en",
        )

        self.assertNotIn("KP-ABCDEF123456", llm.sent)
        self.assertNotIn("93.6% of the cohort", llm.sent)
        self.assertNotIn("contribution 0.16", llm.sent)
        self.assertIn("KP-ABCDEF123456", result["Generated Answer"])
        self.assertIn("93.6% of the cohort", result["Generated Answer"])
        self.assertIn("contribution 0.16", result["Generated Answer"])
        self.assertIn("위험 개요", result["Generated Answer"])
        self.assertEqual(result["References"], references)

    def test_translation_uses_latest_assistant_response(self):
        session = {
            "simple_summary": "Initial summary",
            "messages": [
                {"role": "assistant", "content": "Initial summary"},
                {"role": "user", "content": "What does KCNQ1 do?"},
                {"role": "assistant", "content": "Latest KCNQ1 answer"},
            ],
        }
        self.assertEqual(_latest_assistant_response(session), "Latest KCNQ1 answer")

    def test_disease_aware_prompts_use_minimized_kpredict_context(self):
        class PromptRecorder:
            model = "test/model"

            def __init__(self):
                self.prompts = []

            def chat(self, messages, **_kwargs):
                prompt = messages[-1]["content"]
                self.prompts.append(prompt)
                if "overall_interpretation" in prompt:
                    return '{"overall_interpretation":"Overall.","gene_overview":"Genes."}'
                if "one key: answer" in prompt:
                    return '{"answer":"ok"}'
                return '{"disease_relevance":"ok"}'

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
        agent._generate_gene_section(
            gene="GENE1",
            individual_contribution="selected top-contributor rank only; exact value withheld",
            evidence_context="public evidence",
            citation_rules="none",
            language="en",
        )
        integrated_view = agent._generate_integrated_view(
            selected_genes="GENE1, GENE2",
            top_genes_summary=ranking,
            gene_takeaways="public evidence",
            citation_rules="none",
            language="en",
        )
        self.assertEqual(integrated_view, "Overall.\n\nGenes.")
        agent._generate_followup_text(
            background="public evidence",
            compact_ctx="public evidence",
            ref_index="none",
            question="What does this mean?",
            n_max=0,
        )

        self.assertTrue(all("Gastric Cancer" in prompt for prompt in llm.prompts))
        combined = "\n".join(llm.prompts)
        self.assertIn("exactly one key: disease_relevance", combined)
        self.assertIn("non-specialist reader", combined)
        self.assertIn("no more than three", combined)
        self.assertIn("Do not discuss the overall PRS, percentile, or reference-cohort position", combined)
        self.assertIn("dedicated disclaimer", combined)
        self.assertNotIn("why_it_matters", combined)
        self.assertNotIn("clinical_meaning", combined)
        self.assertNotIn("KP-ABCDEF123456", combined)
        self.assertNotIn("1.23456", combined)
        self.assertIn("exact value withheld", combined)


if __name__ == "__main__":
    unittest.main()
