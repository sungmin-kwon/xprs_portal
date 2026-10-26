from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cohort_registry import get_cohort_config, list_cohorts
from routes.diseases import disease_risk_overview
from schemas import DiseaseRiskOverviewRequest


class CohortRegistryTests(unittest.TestCase):
    def test_private_cohort_is_labeled_kpredict(self):
        cohort = get_cohort_config("kpredict")
        self.assertEqual(cohort.name, "K-PREDICT")
        self.assertEqual(cohort.display_label, "K-PREDICT (private)")

    def test_legacy_kfda_slug_resolves_without_being_advertised(self):
        self.assertEqual(get_cohort_config("kfda").slug, "kpredict")
        self.assertNotIn("kfda", {cohort.slug for cohort in list_cohorts()})

    def test_public_overview_returns_only_configured_public_disease_models(self):
        store = SimpleNamespace(prs_density_data=lambda _individual_id: {
            "percentile": 0.5,
            "prs_value": 1.0,
        })
        request = SimpleNamespace()
        with patch("routes.diseases.load_plot_data_store", return_value=store):
            payload = disease_risk_overview(
                DiseaseRiskOverviewRequest(
                    individual_id="XPRS-DEMO-001",
                    cohort="1000_genomes",
                ),
                request,
            )

        self.assertEqual(
            [disease["slug"] for disease in payload["diseases"]],
            ["breast_cancer"],
        )

    def test_private_overview_includes_disease_linked_panel_counts(self):
        density = {"percentile": 0.91, "prs_value": 1.0, "density": {"x": [0, 1], "y": [0, 1]}}
        panel_counts = {"breast_cancer": {
            "finding_count": 2,
            "alert_count": 1,
            "carrier_count": 1,
        }}
        with (
            patch("routes.diseases.kpredict_root", return_value=SimpleNamespace()),
            patch("routes.diseases.has_kpredict_access", return_value=True),
            patch("routes.diseases.available_diseases", return_value={"breast_cancer": {}}),
            patch("routes.diseases.disease_overview", return_value={"breast_cancer": density}),
            patch("routes.diseases.panel_finding_counts_by_disease", return_value=panel_counts),
        ):
            payload = disease_risk_overview(
                DiseaseRiskOverviewRequest(
                    individual_id="KP-ABCDEF123456",
                    cohort="kpredict",
                ),
                SimpleNamespace(),
            )

        breast = next(item for item in payload["diseases"] if item["slug"] == "breast_cancer")
        self.assertEqual(breast["panel_findings"], panel_counts["breast_cancer"])
        thyroid = next(item for item in payload["diseases"] if item["slug"] == "thyroid_cancer")
        self.assertEqual(thyroid["panel_findings"]["finding_count"], 0)


if __name__ == "__main__":
    unittest.main()
