"""K-PREDICT ``NA_n`` rows: XPRS windows without a gene symbol.

They must stay in gene rankings (they can be strong contributors) but be
labelled by coordinates and never sent to literature providers. Before this,
``NA_1`` was searched in Semantic Scholar (returning materials-science papers)
and shown to clinicians as if it were a gene.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from agents.evidence_assembly import UNANNOTATED_REGION_MODE, EvidenceAssemblyAgent
from agents.gene_importance import KPredictGeneImportanceAgent
from llm_utils import sanitize_kpredict_text
from text_utils import is_unannotated_region, unannotated_region_label


def fake_contribution_frame(_root, _disease, _pid) -> pd.DataFrame:
    return pd.DataFrame({
        "Gene": ["ESR1", "NA_1", "CLIC6*", "NA_2"],
        "contribution": [0.12, -0.0449, -0.0121, -0.001],
        "chr": ["6", "12", "21", "5"],
        "start": [151_600_000, 115_187_070, 34_600_000, 18_811_215],
        "end": [152_100_000, 115_587_070, 34_700_000, 19_211_215],
        "population_rank": [1, 45, 46, 900],
    })


class UnannotatedRegionTests(unittest.TestCase):
    def test_label_uses_coordinates_and_survives_kpredict_sanitizer(self):
        label = unannotated_region_label("12", 115_187_070, 115_587_070)

        self.assertEqual(label, "Unannotated region chr12 115.19–115.59 Mb")
        # The chrN:position form would be replaced by the variant-coordinate filter.
        self.assertEqual(sanitize_kpredict_text(label), label)

    def test_detector_matches_placeholders_and_labels_only(self):
        for name in ["NA_1", "NA_1154", "NA", "Unannotated region chr12 115.19–115.59 Mb"]:
            with self.subTest(name=name):
                self.assertTrue(is_unannotated_region(name))
        for name in ["NAT2", "NAA10", "ESR1", "", None]:
            with self.subTest(name=name):
                self.assertFalse(is_unannotated_region(name))

    def test_gene_agent_relabels_placeholder_rows_and_keeps_them_ranked(self):
        with patch("agents.gene_importance.gene_contribution_frame", fake_contribution_frame):
            agent = KPredictGeneImportanceAgent(Path("/unused"), "breast_cancer")
            bottom = agent.get_bottom_genes("KP-ABCDEF123456", bottom_n=3)

        self.assertEqual(
            list(bottom["Gene"]),
            [
                "Unannotated region chr12 115.19–115.59 Mb",
                "CLIC6",
                "Unannotated region chr5 18.81–19.21 Mb",
            ],
        )

    def test_evidence_retrieval_skips_unannotated_regions(self):
        agent = EvidenceAssemblyAgent.__new__(EvidenceAssemblyAgent)
        agent._retrieve = lambda **_kwargs: self.fail("literature retrieval was attempted")

        for call in (
            lambda: agent.retrieve_gene_context("Unannotated region chr12 115.19–115.59 Mb"),
            lambda: agent.retrieve_gene_context_for_question("NA_1", "Is this region linked to breast cancer?"),
        ):
            self.assertEqual(call(), ([], [], UNANNOTATED_REGION_MODE))


if __name__ == "__main__":
    unittest.main()
