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
        }), pd.DataFrame()

    def get_bottom_genes(self, _pid, bottom_n=5):
        return pd.DataFrame({
            "Gene": ["LOW1"],
            "contribution": [-1.0],
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


class CountingLLM:
    model = "test/model"

    def __init__(self):
        self.calls = 0

    def chat(self, *_args, **_kwargs):
        self.calls += 1
        return "{}"


class SummaryEvidenceGuardTests(unittest.TestCase):
    def test_summary_stops_before_llm_drafting_when_no_citable_evidence_exists(self):
        llm = CountingLLM()
        evidence = EmptyEvidenceAgent()
        agent = ExplanationAgent(
            llm=llm,
            gene_agent=FakeGeneAgent(),
            evidence_agent=evidence,
            ot_agent=None,
        )
        progress = []

        with self.assertRaises(LiteratureEvidenceUnavailableError) as raised:
            agent.build_explanation(
                "HG_TEST",
                gene_count=2,
                progress_callback=progress.append,
            )

        self.assertEqual(llm.calls, 0)
        self.assertEqual(evidence.batch_entries, 1)
        self.assertIn("rate-limiting", str(raised.exception))
        self.assertIn("did not generate an uncited interpretation", str(raised.exception))
        self.assertTrue(any("Summary stopped" in message for message in progress))
        self.assertFalse(any(str(raised.exception) == message for message in progress))


if __name__ == "__main__":
    unittest.main()
