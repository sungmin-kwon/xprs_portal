from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from agents.gene_importance import KPredictGeneImportanceAgent
from kpredict_data import (
    cohort_analysis,
    manhattan_data,
    panel_finding_counts_by_disease,
    rare_findings,
    rare_findings_overview,
    risk_profile,
    panel_gene_options,
    risk_filtered_individuals,
)


class KPredictRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        disease_dir = self.root / "diseases" / "breast_cancer"
        disease_dir.mkdir(parents=True)
        pd.DataFrame([
            {
                "individual_id": "KP-ABCDEF123456",
                "matrix_column": 0,
                "sex": "F",
                "raw_prs": 1.25,
                "z": 0.5,
                "percentile": 69.1,
                "applicable": True,
            }
        ]).to_parquet(disease_dir / "individual_risk.parquet", index=False)
        pd.DataFrame([
            {"matrix_row": 0, "symbol": "GENE1", "mean": 0.1, "variance": 0.5, "chr": 1, "start": 100, "end": 200, "within_region_rank_by_variance": 1},
            {"matrix_row": 1, "symbol": "GENE1*", "mean": 0.1, "variance": 0.4, "chr": 1, "start": 150, "end": 250, "within_region_rank_by_variance": 2},
            {"matrix_row": 2, "symbol": "GENE2", "mean": 0.0, "variance": 0.3, "chr": 2, "start": 300, "end": 400, "within_region_rank_by_variance": 1},
            {"matrix_row": 3, "symbol": "GENE3", "mean": -0.1, "variance": 0.2, "chr": 3, "start": 500, "end": 600, "within_region_rank_by_variance": 1},
        ]).to_parquet(disease_dir / "genes.parquet", index=False)
        np.asarray([0.7, 0.6, -0.4, 0.2], dtype="<f4").tofile(
            disease_dir / "contributions.f32"
        )
        (disease_dir / "matrix.json").write_text(json.dumps({
            "data_file": "contributions.f32",
            "shape": [4, 1],
        }))
        diabetes_dir = self.root / "diseases" / "type2_diabetes"
        diabetes_dir.mkdir(parents=True)
        pd.DataFrame([{
            "individual_id": "KP-ABCDEF123456",
            "matrix_column": 0,
            "sex": "F",
            "raw_prs": 2.5,
            "z": 1.0,
            "percentile": 84.1,
            "applicable": True,
        }]).to_parquet(diabetes_dir / "individual_risk.parquet", index=False)
        pd.DataFrame([
            {"matrix_row": 0, "symbol": "GENE1", "mean": 0.0, "variance": 0.25, "chr": 1, "start": 100, "end": 200, "within_region_rank_by_variance": 1},
            {"matrix_row": 1, "symbol": "GENE4", "mean": 0.0, "variance": 1.0, "chr": 2, "start": 300, "end": 400, "within_region_rank_by_variance": 1},
            {"matrix_row": 2, "symbol": "NA_1", "mean": 0.0, "variance": 0.01, "chr": 3, "start": 500, "end": 600, "within_region_rank_by_variance": 1},
        ]).to_parquet(diabetes_dir / "genes.parquet", index=False)
        np.asarray([2.0, -3.0, 10.0], dtype="<f4").tofile(
            diabetes_dir / "contributions.f32"
        )
        (diabetes_dir / "matrix.json").write_text(json.dumps({
            "data_file": "contributions.f32",
            "shape": [3, 1],
        }))
        (self.root / "manifest.json").write_text(json.dumps({
            "diseases": [
                {"portal_disease_slug": "breast_cancer"},
                {"portal_disease_slug": "type2_diabetes"},
            ],
        }))
        rare_rows = [
            {
                "finding_id": "RF-BREAST",
                "individual_id": "KP-ABCDEF123456",
                "track": "panel",
                "xprs_disease": "breast_cancer",
                "xprs_disease_label": "Breast Cancer",
                "gene": "BRCA1",
                "variant": "1:100:A:G",
                "hgvs": "g.100A>G",
                "rsid": "rs100",
                "genotype": "0/1",
                "moi_call": "alert",
                "moi_why": "dominant panel rule",
                "panelapp_moi": "MONOALLELIC",
                "panelapp_n_panels": 2,
                "clingen_moi": "AD",
                "clingen_tier": "DEFINITIVE",
                "clingen_detail": "ClinGen dosage evidence",
                "clnsig": "Pathogenic",
                "stars": 2,
                "tier": "HIGH",
                "category": "PATH_RARE",
                "consequence": "missense_variant",
                "consequence_class": "missense",
                "clinvar_conditions": "Condition A",
                "gnomad_af": 0.00002,
                "gnomad_af_eas": 0.00003,
                "eas_specific": "EAS_SPECIFIC",
                "cohort_af": 0.0002,
                "qc_pass": True,
                "qc_flags": "",
            },
            {
                "finding_id": "RF-DIABETES",
                "individual_id": "KP-ABCDEF123456",
                "track": "panel",
                "xprs_disease": "diabetes",
                "xprs_disease_label": "Type 2 Diabetes",
                "gene": "GENE-T2D",
                "variant": "2:200:C:T",
                "hgvs": "g.200C>T",
                "rsid": "rs200",
                "genotype": "0/1",
                "moi_call": "carrier",
                "moi_why": "recessive panel rule",
                "clnsig": "Likely pathogenic",
                "stars": 1,
                "tier": "HIGH",
                "consequence": "frameshift_variant",
                "clinvar_conditions": "Condition B",
            },
            {
                "finding_id": "RF-GASTRIC",
                "individual_id": "KP-ABCDEF123456",
                "track": "panel",
                "xprs_disease": "gastric_cancer",
                "xprs_disease_label": "Gastric Cancer",
                "gene": "BRCA1",
                "variant": "1:100:A:G",
                "hgvs": "g.100A>G",
                "rsid": "rs100",
                "genotype": "0/1",
                "moi_call": "alert",
                "moi_why": "dominant panel rule",
                "clnsig": "Pathogenic",
                "stars": 3,
                "tier": "HIGH",
                "consequence": "stop_gained",
                "clinvar_conditions": "Condition C",
            },
            {
                "finding_id": "RF-OTHER",
                "individual_id": "KP-ABCDEF123456",
                "track": "other",
                "xprs_disease": "",
                "xprs_disease_label": "",
                "gene": "OTHER1",
                "variant": "4:400:T:C",
                "hgvs": "g.400T>C",
                "rsid": "rs400",
                "genotype": "0/1",
                "moi_call": "alert",
                "moi_why": "ClinGen rule",
                "clnsig": "Pathogenic",
                "stars": 2,
                "tier": "HIGH",
                "consequence": "missense_variant",
                "clinvar_conditions": "Condition D",
            },
        ]
        pd.DataFrame(rare_rows).to_parquet(self.root / "rare_findings.parquet", index=False)

    def tearDown(self):
        self.temporary.cleanup()

    def test_agent_reads_one_column_and_deduplicates_starred_gene_aliases(self):
        agent = KPredictGeneImportanceAgent(self.root, "breast_cancer")
        top, _ = agent.get_top_genes("KP-ABCDEF123456", top_n=3)
        bottom = agent.get_bottom_genes("KP-ABCDEF123456", bottom_n=2)

        self.assertEqual(list(top["Gene"]), ["GENE1", "GENE3", "GENE2"])
        self.assertEqual(len(set(top["Gene"])), len(top))
        self.assertEqual(list(bottom["Gene"]), ["GENE2", "GENE3"])

    def test_risk_profile_uses_percent_scale_without_exposing_demographics(self):
        profile = risk_profile(self.root, "breast_cancer", "KP-ABCDEF123456")
        self.assertEqual(profile, {"percentile": 69.1, "prs_value": 1.25})
        self.assertNotIn("sex", profile)

    def test_risk_filter_uses_disease_percentiles_without_raw_scores(self):
        payload = risk_filtered_individuals(
            self.root,
            "type2_diabetes",
            percentile_min=80,
            percentile_max=90,
        )

        self.assertEqual(payload["matching_count"], 1)
        self.assertEqual(payload["applicable_count"], 1)
        self.assertEqual(payload["results"], [{
            "individual_id": "KP-ABCDEF123456",
            "percentile": 84.1,
            "rare_status": "carrier",
        }])
        self.assertNotIn("raw_prs", payload["results"][0])
        self.assertNotIn("sex", payload["results"][0])

    def test_cohort_analysis_summarises_panel_findings_without_ids(self):
        payload = cohort_analysis(self.root, "breast_cancer")

        self.assertEqual(payload["summary"]["alert_individual_count"], 1)
        self.assertEqual(payload["summary"]["carrier_individual_count"], 0)
        self.assertEqual(payload["summary"]["no_panel_finding_count"], 0)
        self.assertEqual(payload["summary"]["top_10_alert_overlap_count"], 0)
        # One alert carrier, nobody in the top 10%: none expected there by chance.
        self.assertEqual(payload["summary"]["top_10_alert_expected_count"], 0.0)
        self.assertEqual(payload["points"], [{"gene": "BRCA1", "status": "alert", "percentile": 69.1}])
        self.assertEqual(payload["genes"][0]["gene"], "BRCA1")
        self.assertNotIn("KP-ABCDEF123456", str(payload))

    def test_risk_filter_selects_by_rare_variant_status_and_gene(self):
        def matches(disease, **filters):
            return risk_filtered_individuals(self.root, disease, **filters)["matching_count"]

        self.assertEqual(matches("type2_diabetes", rare_status="carrier"), 1)
        self.assertEqual(matches("type2_diabetes", rare_status="alert"), 0)
        self.assertEqual(matches("type2_diabetes", rare_status="finding", gene="GENE-T2D"), 1)
        self.assertEqual(matches("type2_diabetes", rare_status="all", gene="OTHER"), 0)
        self.assertEqual(matches("breast_cancer", rare_status="none"), 0)
        payload = risk_filtered_individuals(self.root, "breast_cancer", rare_status="alert", gene="BRCA1")
        self.assertEqual(payload["results"][0]["rare_status"], "alert")
        self.assertEqual(payload["applicable_count"], 1)
        with self.assertRaises(ValueError):
            risk_filtered_individuals(self.root, "breast_cancer", rare_status="none", gene="BRCA1")
        with self.assertRaises(ValueError):
            risk_filtered_individuals(self.root, "breast_cancer", rare_status="unknown")

    def test_chat_rare_findings_provider_looks_up_the_individual(self):
        from runtime_agents import rare_findings_provider

        findings = rare_findings_provider(self.root, "breast_cancer")("KP-ABCDEF123456")
        self.assertEqual(findings["individual_id"], "KP-ABCDEF123456")
        self.assertEqual([f["gene"] for f in findings["active_disease_group"]["findings"]], ["BRCA1"])

    def test_panel_gene_options_count_alerts_and_carriers(self):
        self.assertEqual(panel_gene_options(self.root, "type2_diabetes"), [
            {"gene": "GENE-T2D", "individual_count": 1, "alert_count": 0, "carrier_count": 1},
        ])

    def test_panel_finding_counts_are_grouped_by_validated_disease_assignment(self):
        payload = panel_finding_counts_by_disease(self.root, "KP-ABCDEF123456")

        self.assertEqual(payload["breast_cancer"], {
            "finding_count": 1,
            "alert_count": 1,
            "carrier_count": 0,
        })
        self.assertEqual(payload["type2_diabetes"], {
            "finding_count": 1,
            "alert_count": 0,
            "carrier_count": 1,
        })
        self.assertEqual(payload["gastric_cancer"]["alert_count"], 1)
        self.assertNotIn("", payload)

    def test_rare_findings_separate_active_other_panel_and_unassigned_groups(self):
        payload = rare_findings(self.root, "KP-ABCDEF123456", "breast_cancer")

        self.assertEqual(payload["finding_count"], 4)
        self.assertEqual(payload["panel_finding_count"], 3)
        self.assertEqual(payload["unassigned_finding_count"], 1)
        self.assertEqual(payload["active_disease_group"]["finding_count"], 1)
        active_finding = payload["active_disease_group"]["findings"][0]
        self.assertEqual(active_finding["panelapp_moi"], "MONOALLELIC")
        self.assertEqual(active_finding["clingen_tier"], "DEFINITIVE")
        self.assertEqual(active_finding["cohort_af"], 0.0002)
        self.assertEqual(
            [group["disease"] for group in payload["other_disease_groups"]],
            ["type2_diabetes", "gastric_cancer"],
        )
        self.assertEqual(payload["unassigned_group"]["finding_count"], 1)
        self.assertEqual(payload["other_findings"][0]["track"], "other")

    def test_rare_findings_normalize_source_diabetes_id_for_active_disease(self):
        payload = rare_findings(self.root, "KP-ABCDEF123456", "type2_diabetes")

        active = payload["active_disease_group"]
        self.assertEqual(active["disease"], "type2_diabetes")
        self.assertEqual(active["finding_count"], 1)
        self.assertEqual(active["findings"][0]["xprs_disease"], "type2_diabetes")
        self.assertEqual(active["findings"][0]["gene"], "GENE-T2D")

    def test_rare_overview_collapses_repeated_variant_across_disease_panels(self):
        payload = rare_findings_overview(self.root, "KP-ABCDEF123456")

        self.assertEqual(payload["assignment_count"], 4)
        self.assertEqual(payload["variant_count"], 3)
        repeated = next(item for item in payload["variants"] if item["gene"] == "BRCA1")
        self.assertEqual(repeated["assignment_count"], 2)
        self.assertEqual(
            [disease["slug"] for disease in repeated["diseases"]],
            ["breast_cancer", "gastric_cancer"],
        )
        self.assertEqual(repeated["call"], "alert")
        self.assertEqual(len(repeated["panel_assignments"]), 2)
        breast_assignment = repeated["panel_assignments"][0]
        self.assertEqual(breast_assignment["disease"], "breast_cancer")
        self.assertEqual(breast_assignment["moi_why"], "dominant panel rule")
        self.assertEqual(breast_assignment["panelapp_moi"], "MONOALLELIC")
        self.assertEqual(repeated["cohort_af"], 0.0002)


if __name__ == "__main__":
    unittest.main()
