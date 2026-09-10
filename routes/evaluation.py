from __future__ import annotations

import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Cookie, Header, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from config import EVALUATION_RESPONSES_DIR, STATIC_DIR

router = APIRouter()


Background = Literal[
    "computational_genomics",
    "genetics_research",
    "clinician",
    "genetic_counseling",
    "data_science_ai",
    "student",
    "other",
]
Task = Literal[
    "generated_summary",
    "viewed_density_plot",
    "viewed_manhattan_plot",
    "read_gene_explanation",
    "opened_reference",
    "asked_followup",
    "viewed_pdf",
]
CompletionTime = Literal["lt_5", "5_10", "10_15", "15_20", "gt_20"]

RATING_KEYS = {f"q{number}" for number in range(10, 24)}
COMPREHENSION_OPTIONS = {
    "q24": {"clinical_diagnosis", "reference_position", "guaranteed_outcome", "treatment_recommendation"},
    "q25": {"strong_contribution", "definite_disease", "clinical_target", "no_score_relationship"},
    "q26": {"gene_disease_context", "personalized_diagnosis", "treatment_plan", "literature_replacement"},
}


class EvaluationSubmission(BaseModel):
    schema_version: Literal["pilot-v1"] = "pilot-v1"
    prototype_acknowledged: bool
    consented: bool
    participant_id: str = Field(min_length=1, max_length=80)
    portal_session_id: str | None = Field(default=None, max_length=100)
    background: Background
    background_other: str | None = Field(default=None, max_length=200)
    prs_familiarity: int = Field(ge=1, le=5)
    xprs_familiarity: int = Field(ge=1, le=5)
    completed_tasks: list[Task] = Field(default_factory=list, max_length=7)
    completion_time: CompletionTime
    ratings: dict[str, int]
    comprehension: dict[str, str]
    most_useful: str = Field(min_length=1, max_length=4000)
    confusing_or_missing: str = Field(min_length=1, max_length=4000)
    understanding_impact: str = Field(min_length=1, max_length=4000)
    most_important_improvement: str = Field(min_length=1, max_length=4000)

    @field_validator(
        "participant_id",
        "most_useful",
        "confusing_or_missing",
        "understanding_impact",
        "most_important_improvement",
    )
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("field must not be blank")
        return stripped

    @field_validator("portal_session_id", "background_other")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("completed_tasks")
    @classmethod
    def completed_tasks_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("completed_tasks must not contain duplicates")
        return value

    @field_validator("ratings")
    @classmethod
    def validate_ratings(cls, value: dict[str, int]) -> dict[str, int]:
        if set(value) != RATING_KEYS:
            raise ValueError("ratings must contain exactly q10 through q23")
        if any(not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5 for score in value.values()):
            raise ValueError("each rating must be an integer from 1 to 5")
        return value

    @field_validator("comprehension")
    @classmethod
    def validate_comprehension(cls, value: dict[str, str]) -> dict[str, str]:
        if set(value) != set(COMPREHENSION_OPTIONS):
            raise ValueError("comprehension must contain exactly q24 through q26")
        for question, answer in value.items():
            if answer not in COMPREHENSION_OPTIONS[question]:
                raise ValueError(f"invalid answer for {question}")
        return value

    @model_validator(mode="after")
    def validate_consent_and_other(self) -> "EvaluationSubmission":
        if not self.prototype_acknowledged or not self.consented:
            raise ValueError("prototype acknowledgement and consent are required")
        if self.background == "other" and not self.background_other:
            raise ValueError("background_other is required when background is other")
        return self


class EvaluationReceipt(BaseModel):
    response_id: str
    submitted_at: str


def _evaluation_token() -> str:
    return os.getenv("XPRS_EVALUATION_TOKEN", "").strip()


def _require_evaluation_access(supplied: str | None) -> None:
    expected = _evaluation_token()
    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=404, detail="Not found")


def _store_response(record: dict, directory: Path = EVALUATION_RESPONSES_DIR) -> None:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        pass

    destination = directory / f"{record['response_id']}.json"
    temporary = directory / f".{record['response_id']}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


@router.get("/evaluation", include_in_schema=False)
def evaluation_page():
    if not _evaluation_token():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        STATIC_DIR / "evaluation.html",
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"},
    )


@router.post("/api/evaluation/access", include_in_schema=False)
def establish_evaluation_access(
    response: Response,
    x_xprs_evaluation_token: str | None = Header(default=None),
    xprs_evaluation_access: str | None = Cookie(default=None),
) -> None:
    supplied = x_xprs_evaluation_token or xprs_evaluation_access
    _require_evaluation_access(supplied)
    response.headers["Cache-Control"] = "no-store"
    if x_xprs_evaluation_token:
        response.set_cookie(
            "xprs_evaluation_access",
            x_xprs_evaluation_token,
            max_age=8 * 60 * 60,
            httponly=True,
            samesite="strict",
            secure=os.getenv("XPRS_COOKIE_SECURE", "false").lower() in {"1", "true", "yes", "on"},
        )


@router.post(
    "/api/evaluation/responses",
    response_model=EvaluationReceipt,
    include_in_schema=False,
)
def submit_evaluation(
    submission: EvaluationSubmission,
    response: Response,
    x_xprs_evaluation_token: str | None = Header(default=None),
    xprs_evaluation_access: str | None = Cookie(default=None),
):
    _require_evaluation_access(x_xprs_evaluation_token or xprs_evaluation_access)
    response.headers["Cache-Control"] = "no-store"
    submitted_at = datetime.now(timezone.utc).isoformat()
    response_id = str(uuid.uuid4())
    record = {
        "response_id": response_id,
        "submitted_at": submitted_at,
        **submission.model_dump(mode="json"),
    }
    _store_response(record)
    return EvaluationReceipt(response_id=response_id, submitted_at=submitted_at)
