from __future__ import annotations

import unittest
from unittest.mock import patch

from starlette.requests import Request

from routes.reports import export_pdf_report
from schemas import ReportPdfRequest
from tests.support import ROOT


def request() -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/report/pdf",
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
    })


class PdfDownloadRecoveryTests(unittest.TestCase):
    def test_pdf_response_is_length_delimited(self):
        session = {
            "cohort": "1000_genomes",
            "generation_model": "openai/gpt-5.6-sol",
        }
        payload = ReportPdfRequest(
            session_id="session-id",
            individual_id="HG00436",
            disease="breast_cancer",
        )
        with (
            patch("routes.reports.load_session_log_by_id", return_value=session),
            patch("routes.reports.build_pdf_report", return_value=b"%PDF-test"),
        ):
            response = export_pdf_report(payload, request())

        self.assertEqual(response.body, b"%PDF-test")
        self.assertEqual(response.headers["content-length"], str(len(b"%PDF-test")))
        self.assertEqual(response.media_type, "application/pdf")

    def test_dashboard_retries_only_interrupted_pdf_downloads(self):
        script = (ROOT / "static" / "dashboard.js").read_text(encoding="utf-8")

        self.assertIn("networkRetryDelaysMs: [0, 750]", script)
        self.assertIn("if (!(error instanceof TypeError)", script)
        self.assertIn("if (pdfDownloadInProgress) return;", script)
        self.assertIn('t("exportPdfRetrying")', script)


if __name__ == "__main__":
    unittest.main()
