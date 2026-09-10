#!/usr/bin/env python3
"""Export private pilot-evaluation JSON responses to one analysis-ready CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESPONSES_DIR = ROOT / "evaluation_responses"
RATING_GROUPS = {
    "usability_mean": ("q10", "q11"),
    "explainability_mean": ("q12", "q13", "q14"),
    "visualization_mean": ("q15",),
    "evidence_trust_mean": ("q16", "q17"),
    "followup_chat_mean": ("q18", "q19"),
    "pdf_report_mean": ("q20",),
    "overall_value_mean": ("q21", "q22", "q23"),
}
TASK_KEYS = (
    "generated_summary",
    "viewed_density_plot",
    "viewed_manhattan_plot",
    "read_gene_explanation",
    "opened_reference",
    "asked_followup",
    "viewed_pdf",
)
CORRECT_COMPREHENSION = {
    "q24": "reference_position",
    "q25": "strong_contribution",
    "q26": "gene_disease_context",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses-dir", type=Path, default=DEFAULT_RESPONSES_DIR)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def mean(values: list[int]) -> str:
    return f"{sum(values) / len(values):.3f}" if values else ""


def flatten(record: dict) -> dict:
    ratings = record.get("ratings") or {}
    comprehension = record.get("comprehension") or {}
    tasks = set(record.get("completed_tasks") or [])
    row = {
        "response_id": record.get("response_id", ""),
        "submitted_at": record.get("submitted_at", ""),
        "schema_version": record.get("schema_version", ""),
        "participant_id": record.get("participant_id", ""),
        "portal_session_id": record.get("portal_session_id") or "",
        "background": record.get("background", ""),
        "background_other": record.get("background_other") or "",
        "prs_familiarity": record.get("prs_familiarity", ""),
        "xprs_familiarity": record.get("xprs_familiarity", ""),
        "completion_time": record.get("completion_time", ""),
        "completed_task_count": len(tasks),
    }
    for task in TASK_KEYS:
        row[f"task_{task}"] = int(task in tasks)
    for question in (f"q{number}" for number in range(10, 24)):
        row[question] = ratings.get(question, "")
    for label, questions in RATING_GROUPS.items():
        scores = [ratings[q] for q in questions if isinstance(ratings.get(q), int)]
        row[label] = mean(scores) if len(scores) == len(questions) else ""
    correct_count = 0
    for question, correct_answer in CORRECT_COMPREHENSION.items():
        answer = comprehension.get(question, "")
        is_correct = answer == correct_answer
        row[question] = answer
        row[f"{question}_correct"] = int(is_correct)
        correct_count += int(is_correct)
    row["comprehension_correct_count"] = correct_count
    row["most_useful"] = record.get("most_useful", "")
    row["confusing_or_missing"] = record.get("confusing_or_missing", "")
    row["understanding_impact"] = record.get("understanding_impact", "")
    row["most_important_improvement"] = record.get("most_important_improvement", "")
    return row


def main() -> int:
    args = parse_args()
    responses_dir = args.responses_dir.resolve()
    output = (args.output or responses_dir / "evaluation_export.csv").resolve()
    files = sorted(responses_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"No response JSON files found in {responses_dir}")

    rows = [flatten(json.loads(path.read_text(encoding="utf-8"))) for path in files]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Exported {len(rows)} response(s) to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
