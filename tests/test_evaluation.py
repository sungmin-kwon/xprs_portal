from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, Response
from pydantic import ValidationError
from routes.evaluation import (
    EvaluationSubmission,
    _require_evaluation_access,
    _store_response,
    establish_evaluation_access,
    evaluation_page,
    submit_evaluation,
)
from routes.individuals import get_app_info
from scripts.export_evaluation_responses import flatten


def valid_payload() -> dict:
    return {
        "schema_version": "pilot-v1",
        "prototype_acknowledged": True,
        "consented": True,
        "participant_id": "P-001",
        "portal_session_id": "session-one",
        "background": "computational_genomics",
        "background_other": None,
        "prs_familiarity": 4,
        "xprs_familiarity": 3,
        "completed_tasks": ["generated_summary", "viewed_density_plot"],
        "completion_time": "10_15",
        "ratings": {f"q{number}": 4 for number in range(10, 24)},
        "comprehension": {
            "q24": "reference_position",
            "q25": "strong_contribution",
            "q26": "gene_disease_context",
        },
        "most_useful": "The evidence viewer.",
        "confusing_or_missing": "The percentile explanation.",
        "understanding_impact": "Yes, citations supplied context.",
        "most_important_improvement": "Make the first load faster.",
    }


class EvaluationAccessTests(unittest.TestCase):
    def test_evaluation_is_disabled_when_token_is_unset(self):
        with patch.dict(os.environ, {"XPRS_EVALUATION_TOKEN": ""}):
            with self.assertRaises(HTTPException) as raised:
                _require_evaluation_access("anything")
        self.assertEqual(raised.exception.status_code, 404)

    def test_page_is_available_only_when_evaluation_is_enabled(self):
        with patch.dict(os.environ, {"XPRS_EVALUATION_TOKEN": ""}):
            with self.assertRaises(HTTPException):
                evaluation_page()
        with patch.dict(os.environ, {"XPRS_EVALUATION_TOKEN": "study-token"}):
            result = evaluation_page()
        self.assertEqual(result.headers["x-robots-tag"], "noindex, nofollow")

    def test_fragment_token_exchange_sets_http_only_cookie(self):
        with patch.dict(os.environ, {"XPRS_EVALUATION_TOKEN": "study-token"}):
            result = Response()
            establish_evaluation_access(
                result,
                x_xprs_evaluation_token="study-token",
                xprs_evaluation_access=None,
            )
        cookie = result.headers.get("set-cookie", "")
        self.assertIn("xprs_evaluation_access=study-token", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie)

    def test_existing_access_cookie_does_not_get_reissued(self):
        with patch.dict(os.environ, {"XPRS_EVALUATION_TOKEN": "study-token"}):
            result = Response()
            establish_evaluation_access(
                result,
                x_xprs_evaluation_token=None,
                xprs_evaluation_access="study-token",
            )
        self.assertNotIn("set-cookie", result.headers)

    def test_app_info_reports_whether_evaluation_is_enabled(self):
        with (
            patch("runtime_agents.get_runtime_agents", return_value={"llm_model": "test/model"}),
            patch.dict(os.environ, {"XPRS_EVALUATION_TOKEN": ""}),
        ):
            self.assertFalse(get_app_info()["evaluation_enabled"])
        with (
            patch("runtime_agents.get_runtime_agents", return_value={"llm_model": "test/model"}),
            patch.dict(os.environ, {"XPRS_EVALUATION_TOKEN": "study-token"}),
        ):
            self.assertTrue(get_app_info()["evaluation_enabled"])


class EvaluationValidationTests(unittest.TestCase):
    def test_valid_instrument_has_all_fourteen_rating_items(self):
        submission = EvaluationSubmission(**valid_payload())
        self.assertEqual(len(submission.ratings), 14)

    def test_consent_is_required(self):
        payload = valid_payload()
        payload["consented"] = False
        with self.assertRaises(ValidationError):
            EvaluationSubmission(**payload)

    def test_all_rating_items_are_required(self):
        payload = valid_payload()
        payload["ratings"].pop("q23")
        with self.assertRaises(ValidationError):
            EvaluationSubmission(**payload)

    def test_other_background_requires_description(self):
        payload = valid_payload()
        payload["background"] = "other"
        with self.assertRaises(ValidationError):
            EvaluationSubmission(**payload)


class EvaluationStorageTests(unittest.TestCase):
    def test_response_file_is_private_and_contains_no_request_metadata(self):
        record = {
            "response_id": "receipt-one",
            "submitted_at": "2026-09-03T00:00:00+00:00",
            **valid_payload(),
        }
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "responses"
            _store_response(record, directory)
            path = directory / "receipt-one.json"
            restored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(restored["participant_id"], "P-001")
            self.assertNotIn("ip_address", restored)
            self.assertNotIn("user_agent", restored)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_submission_returns_receipt_and_passes_validated_record_to_storage(self):
        captured = []
        submission = EvaluationSubmission(**valid_payload())
        with (
            patch.dict(os.environ, {"XPRS_EVALUATION_TOKEN": "study-token"}),
            patch("routes.evaluation._store_response", side_effect=captured.append),
        ):
            receipt = submit_evaluation(
                submission,
                Response(),
                x_xprs_evaluation_token="study-token",
                xprs_evaluation_access=None,
            )
        self.assertEqual(captured[0]["response_id"], receipt.response_id)
        self.assertEqual(captured[0]["schema_version"], "pilot-v1")

    def test_csv_flattening_calculates_prespecified_descriptive_scores(self):
        record = {
            "response_id": "receipt-one",
            "submitted_at": "2026-09-03T00:00:00+00:00",
            **valid_payload(),
        }
        row = flatten(record)
        self.assertEqual(row["usability_mean"], "4.000")
        self.assertEqual(row["completed_task_count"], 2)
        self.assertEqual(row["comprehension_correct_count"], 3)


if __name__ == "__main__":
    unittest.main()
