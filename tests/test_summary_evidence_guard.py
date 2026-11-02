from __future__ import annotations

import unittest
from contextlib import contextmanager

import pandas as pd

from agents.explanation import ExplanationAgent, LiteratureEvidenceUnavailableError


class FakeGeneAgent:
    default_top_n = 5

    def get_top_genes(self, _pid, top_n=5):
        genes = ["GENE1", "GENE2", "GENE3", "GENE4", "GENE5"]
        return pd.DataFrame({
            "Gene": genes[:top_n],
            "contribution": [5.0, 4.0, 3.0, 2.0, 1.0][:top_n],
            "population_rank": list(range(1, top_n + 1)),
        }), pd.DataFrame()

    def get_bottom_genes(self, _pid, bottom_n=5):
        return pd.DataFrame({
            "Gene": ["LOW1"],
            "contribution": [-1.0],
            "population_rank": [1],
        })


class FakeS2:
    def get_health_status(self):
        return {"last_status_code": 429}


class EmptyEvidenceAgent:
    s2 = FakeS2()

    def __init__(self):
        self.batch_entries = 0

    @contextmanager
    def interactive_request_batch(self, _progress_callback=None):
        self.batch_entries += 1
        yield

    def retrieve_gene_context(self, _gene, top_k=10, progress_callback=None):
        return [], [], "RAG_DENSE_PRIMARY_DISEASE"


class VerboseEvidenceAgent(EmptyEvidenceAgent):
    def retrieve_gene_context(self, gene, top_k=10, progress_callback=None):
        if progress_callback:
            progress_callback(f'Gathering literature context for "{gene}"')
            progress_callback(f'Sending query to Europe PMC: "{gene}" (public API)')
            progress_callback(f'Indexing 5 eligible Europe PMC documents for "{gene}"')
        return (
            [f"Evidence for {gene}."],
            [{"paperId": f"PMID:{gene}", "title": f"{gene} study"}],
            "RAG_MEDCPT_PRIMARY_DISEASE",
        )


class CountingLLM:
    model = "test/model"

    def __init__(self):
        self.calls = 0

    def chat(self, *_args, **_kwargs):
        self.calls += 1
        return "{}"


class SummaryEvidenceGuardTests(unittest.TestCase):
    def test_summary_continues_without_uncited_literature_claims(self):
        llm = CountingLLM()
        evidence = EmptyEvidenceAgent()
        agent = ExplanationAgent(
            llm=llm,
            gene_agent=FakeGeneAgent(),
            evidence_agent=evidence,
            ot_agent=None,
        )
        progress = []

        result = agent.build_explanation(
            "HG_TEST",
            gene_count=2,
            progress_callback=progress.append,
        )

        self.assertGreater(llm.calls, 0)
        self.assertEqual(evidence.batch_entries, 1)
        self.assertIn("Top 5 (risk-increasing)", result["Simple Explanation"])
        self.assertIn("Bottom 5 (risk-lowering)", result["Simple Explanation"])
        self.assertTrue(any("will continue" in message for message in progress))

    def test_summary_progress_collapses_provider_details_and_report_sections(self):
        progress = []
        agent = ExplanationAgent(
            llm=CountingLLM(),
            gene_agent=FakeGeneAgent(),
            evidence_agent=VerboseEvidenceAgent(),
            ot_agent=None,
        )

        result = agent.build_explanation(
            "HG_TEST",
            gene_count=2,
            progress_callback=progress.append,
        )

        self.assertTrue(any(message.startswith("Retrieving literature for") for message in progress))
        self.assertTrue(any(message.startswith("Literature sources:") for message in progress))
        self.assertFalse(any("Sending query to Europe PMC" in message for message in progress))
        for section in result["Report Payload"]["gene_sections"]:
            self.assertIn("disease_relevance", section)
            self.assertNotIn("why_it_matters", section)
            self.assertNotIn("clinical_meaning", section)
        self.assertNotIn("key_findings", result["Report Payload"])


if __name__ == "__main__":
    unittest.main()
