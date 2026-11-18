from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kpredict_data import risk_profile
from routes import kpredict


class DiseaseNameValidationTests(unittest.TestCase):
    """Disease names come from request parameters and must not become arbitrary paths."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        folder = self.root / "diseases" / "breast_cancer"
        folder.mkdir(parents=True)
        pd.DataFrame({
            "individual_id": ["person-1"], "matrix_column": [0], "sex": ["F"],
            "raw_prs": [1.0], "z": [0.5], "percentile": [69.0], "applicable": [True],
        }).to_parquet(folder / "individual_risk.parquet", index=False)
        (self.root / "manifest.json").write_text(json.dumps({"diseases": [{"portal_disease_slug": "breast_cancer"}]}))

    def tearDown(self):
        self.temporary.cleanup()

    def test_listed_disease_is_read(self):
        self.assertAlmostEqual(risk_profile(self.root, "breast_cancer", "person-1")["percentile"], 69.0)

    def test_unknown_or_path_like_disease_is_rejected(self):
        for disease in ("not_a_disease", "../breast_cancer", "breast_cancer/../breast_cancer", ""):
            with self.subTest(disease=disease), self.assertRaisesRegex(ValueError, "Unknown disease"):
                risk_profile(self.root, disease, "person-1")

    def test_unknown_disease_returns_404_not_500(self):
        environment = {"KPREDICT_ENABLED": "true", "KPREDICT_DATA_ROOT": str(self.root),
                       "XPRS_KPREDICT_TOKEN": "cohort-secret", "XPRS_ADMIN_TOKEN": "admin-secret"}
        with patch.dict(os.environ, environment):
            app = FastAPI()
            app.include_router(kpredict.router)
            response = TestClient(app, raise_server_exceptions=False).get(
                "/api/kpredict/disease-evidence",
                params={"individual_id": "person-1", "disease": "not_a_disease"},
                headers={"X-XPRS-KPREDICT-Token": "cohort-secret"},
            )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
