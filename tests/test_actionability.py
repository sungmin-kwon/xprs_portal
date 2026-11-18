from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from actionability import matching_reports
from kpredict_data import _with_actionability

REPORTS = {"reports": [
    {"doc_id": "AC1", "context": "Adult", "condition": "Hereditary Breast and Ovarian Cancer", "genes": ["BRCA2"],
     "inheritance": ["autosomal dominant"], "outcomes": [{"intervention": "Surveillance", "outcome": "Breast cancer"}],
     "url": "https://actionability.clinicalgenome.org/ac/Adult/ui/stg2SummaryRpt?doc=AC1"},
    {"doc_id": "AC2", "context": "Adult", "condition": "Fanconi Anemia", "genes": ["BRCA2"],
     "inheritance": ["autosomal recessive"], "outcomes": [], "url": ""},
    {"doc_id": "AC3", "context": "Adult", "condition": "Glanzmann thrombasthenia", "genes": ["ITGA2B"],
     "inheritance": ["autosomal recessive"], "outcomes": [], "url": ""},
    {"doc_id": "AC4", "context": "Adult", "condition": "Retinoblastoma", "genes": ["RB1"],
     "inheritance": [], "outcomes": [], "url": ""},
    {"doc_id": "AC5", "context": "Adult", "condition": "Breast Cancer", "genes": ["ATM", "CHEK2"],
     "inheritance": ["autosomal dominant"], "url": "",
     "outcomes": [{"intervention": "Surveillance", "outcome": "Breast Cancer (ATM)"},
                  {"intervention": "Chemoprevention", "outcome": "Breast cancer (CHEK2)"}]},
]}
BRCA2_HBOC = {"gene": "BRCA2", "genotype": "0/1", "clinvar_conditions": "Hereditary breast ovarian cancer syndrome"}


class ActionabilityMatchingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "portal_actionability.json"
        self.path.write_text(json.dumps(REPORTS))

    def tearDown(self):
        self.temporary.cleanup()

    def ids(self, finding):
        return [report["doc_id"] for report in matching_reports(finding, self.path)]

    def test_dominant_report_for_the_same_condition_matches(self):
        self.assertEqual(self.ids(BRCA2_HBOC), ["AC1"])           # not the Fanconi anemia report

    def test_recessive_report_needs_a_homozygous_finding(self):
        finding = {"gene": "ITGA2B", "genotype": "0/1", "clinvar_conditions": "Glanzmann thrombasthenia"}
        self.assertEqual(self.ids(finding), [])
        self.assertEqual(self.ids({**finding, "genotype": "1/1"}), ["AC3"])

    def test_other_conditions_and_unstated_inheritance_do_not_match(self):
        self.assertEqual(self.ids({**BRCA2_HBOC, "clinvar_conditions": "Pancreatic cancer"}), [])
        self.assertEqual(self.ids({"gene": "RB1", "genotype": "0/1", "clinvar_conditions": "Retinoblastoma"}), [])

    def test_multi_gene_fields_are_split(self):
        self.assertEqual(self.ids({**BRCA2_HBOC, "gene": "BRCA2, ZAR1L"}), ["AC1"])

    def test_multi_gene_reports_keep_only_the_findings_gene_rows(self):
        [report] = matching_reports({"gene": "ATM", "genotype": "0/1", "clinvar_conditions": "Familial cancer of breast"}, self.path)
        self.assertEqual([o["outcome"] for o in report["outcomes"]], ["Breast Cancer (ATM)"])
        self.assertEqual(report["interventions"], ["Surveillance"])

    def test_without_a_reference_file_nothing_is_attached(self):
        with patch.dict(os.environ, {"ACTIONABILITY_REFERENCE_PATH": ""}):
            self.assertEqual(matching_reports(BRCA2_HBOC), [])

    def test_only_alerts_get_references(self):
        with patch.dict(os.environ, {"ACTIONABILITY_REFERENCE_PATH": str(self.path)}):
            self.assertEqual([r["doc_id"] for r in _with_actionability(dict(BRCA2_HBOC), "alert")["actionability"]], ["AC1"])
            self.assertEqual(_with_actionability(dict(BRCA2_HBOC), "carrier")["actionability"], [])


if __name__ == "__main__":
    unittest.main()
