#!/usr/bin/env python3
"""End-to-end test of the chatbot with the clinician question bank.

Asks every question in a question-bank spreadsheet to a running portal, checks
each answer, and writes the answers and check results in spreadsheet order as
JSON (and optionally Markdown).

The question bank (.xlsx; columns "Q ID", "Section", "Topic", "Question (ask in
English)", "Answered well?", "Comment") is private and not stored in this
repository; pass its path.

How questions are asked: each section runs in its own chat session, in
spreadsheet order, starting with "Generate Summary" as a clinician would, so
follow-up questions keep their context. "Track 2" (rare-variant) questions use
an individual with a panel alert for the chosen disease; the other sections an
individual without panel findings. Both are chosen deterministically (lowest
pseudonymous ID that fits) unless given with --individual / --rare-individual.
"[disease]" is replaced by the disease name. A row without an ID continues the
previous question and gets its ID plus "b" (e.g. D11b).

Checks (scripts/question_bank_checks.py): general checks on every answer (no
pseudonymous ID or rsID, percentile not read as a probability, no "has no
pathogenic variants" claim, quoted percentile matches the report) and the
question's entry in benchmarks/question_bank_expectations.json (refusal
expected or not, phrases that must or must not appear).

Exit status: 0 if every answer passes, 1 if a check fails, 2 if a question was
not answered. Results are saved after every question, so an interrupted run
keeps what it has. The output contains pseudonymous K-PREDICT IDs and
individual-level answers: keep it in a private location, never in this
repository.

Access uses the portal's cookie login with XPRS_KPREDICT_TOKEN (or
XPRS_ADMIN_TOKEN) from the environment or the repository's .env; the token is
sent only to --base-url.

Examples:
    # check the spreadsheet and expectations, no model calls
    python scripts/run_question_bank.py --questions BANK.xlsx --dry-run
    # full run
    python scripts/run_question_bank.py --questions BANK.xlsx --out PRIVATE/run.json --markdown PRIVATE/run.md
    # a few questions only
    python scripts/run_question_bank.py --questions BANK.xlsx --only D01,T02 --out PRIVATE/quick.json
    # re-check a saved run after editing expectations, and compare with an earlier run
    python scripts/run_question_bank.py --rescore PRIVATE/run.json --compare PRIVATE/previous.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values

try:  # run as a script (python scripts/run_question_bank.py) or imported as scripts.run_question_bank
    from question_bank_checks import (DEFAULT_EXPECTATIONS, expectation_checks, failure_texts, general_checks,
                                      load_expectations, refusal_texts)
except ImportError:
    from scripts.question_bank_checks import (DEFAULT_EXPECTATIONS, expectation_checks, failure_texts,
                                              general_checks, load_expectations, refusal_texts)

REPO_ROOT = Path(__file__).resolve().parents[1]
RARE_SECTION = "Track 2"
TASK_TIMEOUT_SECONDS = 900
POLL_SECONDS = 2.0
XLSX_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
EXPECTED_COLUMNS = {
    "id": "Q ID",
    "section": "Section",
    "topic": "Topic",
    "question": "Question (ask in English)",
    "rating": "Answered well?",
    "comment": "Comment",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--questions", type=Path, help="Question bank spreadsheet (.xlsx)")
    parser.add_argument("--out", type=Path, help="JSON output path (private location)")
    parser.add_argument("--markdown", type=Path, help="Optional Markdown copy for reading")
    parser.add_argument("--expectations", type=Path, default=DEFAULT_EXPECTATIONS,
                        help="Per-question expectations (default: benchmarks/question_bank_expectations.json)")
    parser.add_argument("--base-url", default="http://127.0.0.1:9009")
    parser.add_argument("--disease", default="breast_cancer", help="K-PREDICT disease slug")
    parser.add_argument("--model", help="Generation model id; default: the portal's default model")
    parser.add_argument("--language", default="en")
    parser.add_argument("--individual", help="Individual for the non-rare-variant sections")
    parser.add_argument("--rare-individual", help="Individual for the Track 2 (rare-variant) section")
    parser.add_argument("--only", help="Comma-separated question IDs to ask (e.g. D01,D04,T08)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Check the question bank and expectations without calling the portal")
    parser.add_argument("--rescore", type=Path,
                        help="Re-check a saved run JSON (e.g. after editing expectations) without asking again")
    parser.add_argument("--compare", type=Path, help="Earlier run JSON: list questions whose pass/fail changed")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Question bank
# ---------------------------------------------------------------------------

def _xlsx_rows(path: Path) -> list[list[str]]:
    """Rows of the first worksheet as strings (stdlib only; no openpyxl needed)."""
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            for item in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("m:si", XLSX_NS):
                shared.append("".join(t.text or "" for t in item.iter(f"{{{XLSX_NS['m']}}}t")))
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {rel.get("Id"): rel.get("Target") for rel in relations}
        first_sheet = workbook.find("m:sheets", XLSX_NS)[0]
        target = targets[first_sheet.get(f"{{{XLSX_NS['r']}}}id")].lstrip("/")
        sheet = ET.fromstring(archive.read(target if target.startswith("xl/") else f"xl/{target}"))
    rows: list[list[str]] = []
    for row in sheet.iter(f"{{{XLSX_NS['m']}}}row"):
        cells: dict[int, str] = {}
        for cell in row.findall("m:c", XLSX_NS):
            letters = re.match(r"[A-Z]+", cell.get("r")).group()
            column = 0
            for letter in letters:
                column = column * 26 + ord(letter) - 64
            value = cell.find("m:v", XLSX_NS)
            kind = cell.get("t")
            if kind == "s" and value is not None:
                text = shared[int(value.text)]
            elif kind == "inlineStr":
                text = "".join(t.text or "" for t in cell.iter(f"{{{XLSX_NS['m']}}}t"))
            else:
                text = value.text if value is not None and value.text else ""
            cells[column - 1] = text.strip()
        rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
    return rows


def load_questions(path: Path) -> list[dict]:
    """Questions in spreadsheet order: id, section, topic, question, clinician rating and comment."""
    rows = _xlsx_rows(path)
    header = rows[0]
    missing = [name for name in EXPECTED_COLUMNS.values() if name not in header]
    if missing:
        raise SystemExit(f"Question bank is missing columns: {missing}")
    index = {key: header.index(name) for key, name in EXPECTED_COLUMNS.items()}
    questions: list[dict] = []
    for row in rows[1:]:
        cell = {key: (row[i] if i < len(row) else "") for key, i in index.items()}
        if not cell["question"]:
            continue
        if not cell["id"]:
            # A follow-up row without an ID continues the previous question (e.g. D11 -> D11b).
            previous = questions[-1]
            cell["id"] = f"{previous['id']}b"
            cell["section"] = cell["section"] or previous["section"]
            cell["topic"] = cell["topic"] or previous["topic"]
        questions.append(cell)
    return questions


# ---------------------------------------------------------------------------
# Portal access
# ---------------------------------------------------------------------------

def access_token() -> str:
    env_file = dotenv_values(REPO_ROOT / ".env") if (REPO_ROOT / ".env").is_file() else {}
    for name in ("XPRS_KPREDICT_TOKEN", "XPRS_ADMIN_TOKEN"):
        value = (os.getenv(name) or env_file.get(name) or "").strip()
        if value:
            return value
    raise SystemExit("Set XPRS_KPREDICT_TOKEN (or XPRS_ADMIN_TOKEN) in the environment or .env")


def login(client: httpx.Client) -> None:
    """Exchange the token for the portal's access cookie (kept in the client's cookie jar)."""
    response = client.post("/api/kpredict/access", headers={"X-XPRS-KPREDICT-Token": access_token()})
    response.raise_for_status()


def run_task(client: httpx.Client, path: str, payload: dict) -> dict:
    """Start an asynchronous summary/chat task and wait for its result."""
    response = client.post(path, json=payload)
    response.raise_for_status()
    task_id = response.json()["task_id"]
    deadline = time.monotonic() + TASK_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        state = client.get(f"/api/tasks/{task_id}").json()
        if state["status"] == "complete":
            return state["result"] or {}
        if state["status"] == "failed":
            raise RuntimeError(state.get("error") or "task failed")
        time.sleep(POLL_SECONDS)
    raise TimeoutError(f"no result after {TASK_TIMEOUT_SECONDS} s")


def finder(client: httpx.Client, disease: str, rare_status: str) -> dict:
    response = client.get("/api/kpredict/individual-risk-filter",
                          params={"disease": disease, "rare_status": rare_status, "limit": 5000})
    response.raise_for_status()
    return response.json()


def pick_general_individual(client: httpx.Client, disease: str) -> str:
    """Lowest ID among applicable individuals without a panel finding for the disease."""
    results = finder(client, disease, "none")["results"]
    if not results:
        raise SystemExit("No individual without panel findings for this disease")
    return min(row["individual_id"] for row in results)


def pick_rare_individual(client: httpx.Client, disease: str) -> str:
    """Lowest ID with a panel alert for the disease and at least one other finding.

    Track 2 asks about findings on other panels and carrier findings, so an
    individual with only the one alert would leave those questions empty.
    """
    candidates = sorted(row["individual_id"] for row in finder(client, disease, "alert")["results"])
    for individual_id in candidates:
        response = client.get("/api/kpredict/rare-findings", params={"individual_id": individual_id, "disease": disease})
        response.raise_for_status()
        data = response.json()
        others = len(data.get("other_disease_groups") or []) + len((data.get("unassigned_group") or {}).get("findings") or [])
        if others:
            return individual_id
    if candidates:
        return candidates[0]
    raise SystemExit("No individual with a panel alert for this disease")


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def portal_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_markdown(path: Path, payload: dict) -> None:
    run, summary = payload["run"], payload["summary"]
    lines = [
        f"# Question bank run, {run['started_at'][:16].replace('T', ' ')} UTC",
        "",
        f"- Disease: {run['disease_label']}; model: {run['model_requested'] or run['default_model']}; "
        f"portal commit: {run['portal_commit']}",
        f"- Answered {summary['answered']} of {summary['questions']}; checks passed for "
        f"{summary['questions_passed']} of {summary['questions']} questions",
        "- Contains pseudonymous IDs and individual-level answers: keep private.",
        "",
        "| ID | Section | Result | Failed checks |",
        "|---|---|---|---|",
    ]
    for result in payload["results"]:
        failed = "; ".join(f"{c['check']} ({c['detail']})" if c["detail"] else c["check"]
                           for c in result["checks"] if not c["passed"])
        lines.append(f"| {result['id']} | {result['section']} | {'pass' if result['passed'] else 'FAIL'} | {failed} |")
    lines.append("")
    for result in payload["results"]:
        lines += [f"## {result['id']} · {result['section']} · {result['topic']}", "", f"**Q:** {result['asked']}", ""]
        if result.get("expectation_reason"):
            lines += [f"*Expected:* {result['expectation_reason']}", ""]
        if result["clinician_rating"] or result["clinician_comment"]:
            lines += [f"*Clinician (earlier round):* {result['clinician_rating'] or '—'}"
                      f"{' — ' + result['clinician_comment'] if result['clinician_comment'] else ''}", ""]
        lines += [result["answer"] if result["status"] == "ok" else f"**{result['status']}:** {result['error']}", ""]
        if result["references"]:
            lines += ["References: " + "; ".join(r.get("title") or "untitled" for r in result["references"]), ""]
        lines += [f"*{result['seconds']} s · {'pass' if result['passed'] else 'FAIL'}*", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Checks, report, comparison
# ---------------------------------------------------------------------------

def score(payload: dict, expectations: dict[str, dict]) -> None:
    """(Re)compute the checks for every result and the run summary, in place."""
    refusals = refusal_texts()
    failures = failure_texts()
    percentiles = payload["run"].get("percentiles", {})
    for result in payload["results"]:
        if result["status"] != "ok":
            result["checks"] = [{"check": "answered", "passed": False, "detail": result["error"] or result["status"]}]
        else:
            expectation = expectations.get(result["id"], {})
            result["checks"] = (general_checks(result["answer"], percentile=percentiles.get(result["individual_role"]),
                                               failures=failures)
                                + expectation_checks(result["answer"], expectation, refusals))
            result["expectation_reason"] = expectation.get("reason", "")
        result["passed"] = all(check["passed"] for check in result["checks"])
    results = payload["results"]
    payload["summary"] = {
        "questions": len(results),
        # A portal failure message is returned as a normal answer; count it as unanswered.
        "answered": sum(r["status"] == "ok" and r["checks"][0]["passed"] for r in results),
        "questions_passed": sum(r["passed"] for r in results),
        "questions_with_expectations": sum(r["id"] in expectations for r in results),
        "failed": [r["id"] for r in results if not r["passed"]],
    }


def print_report(payload: dict) -> None:
    summary = payload["summary"]
    print(f"\nAnswered {summary['answered']}/{summary['questions']}; "
          f"passed {summary['questions_passed']}/{summary['questions']} "
          f"({summary['questions_with_expectations']} with question-specific expectations)")
    for result in payload["results"]:
        if result["passed"]:
            continue
        failed = ", ".join(f"{c['check']}: {c['detail']}" if c["detail"] else c["check"]
                           for c in result["checks"] if not c["passed"])
        print(f"  FAIL {result['id']:5} {failed}")


def print_comparison(payload: dict, previous_path: Path) -> None:
    """Questions whose pass/fail result changed since an earlier run."""
    previous = {r["id"]: r for r in json.loads(previous_path.read_text(encoding="utf-8"))["results"]}
    changes = []
    for result in payload["results"]:
        before = previous.get(result["id"])
        if before is None or "passed" not in before:
            continue
        if before["passed"] != result["passed"]:
            changes.append(f"  {result['id']:5} {'FAIL -> pass' if result['passed'] else 'pass -> FAIL'}")
    print(f"\nCompared with {previous_path.name}: {len(changes)} change(s)")
    print("\n".join(changes) if changes else "  no pass/fail changes")


def exit_code(payload: dict) -> int:
    """0: all passed; 1: a check failed; 2: a question was not answered."""
    summary = payload["summary"]
    if summary["answered"] < summary["questions"]:
        return 2
    return 0 if summary["questions_passed"] == summary["questions"] else 1


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def select_questions(questions: list[dict], only: str | None) -> list[dict]:
    if not only:
        return questions
    wanted = {item.strip() for item in only.split(",") if item.strip()}
    selected = [q for q in questions if q["id"] in wanted]
    if not selected:
        raise SystemExit("--only matched no question IDs")
    return selected


def dry_run(questions: list[dict], expectations: dict[str, dict]) -> int:
    ids = [q["id"] for q in questions]
    sections = list(dict.fromkeys(q["section"] for q in questions))
    unknown = sorted(set(expectations) - set(ids))
    print(f"{len(questions)} questions in {len(sections)} sections: {', '.join(sections)}")
    print(f"{sum(i in expectations for i in ids)} with question-specific expectations; "
          f"{len(questions) - sum(i in expectations for i in ids)} with general checks only")
    if unknown:
        print(f"Expectations for IDs not in the question bank: {unknown}")
        return 1
    return 0


def ask_all(args: argparse.Namespace, questions: list[dict], expectations: dict[str, dict]) -> dict:
    """Ask every question on the portal; returns the run payload (also saved after each answer)."""
    out = args.out.expanduser()
    with httpx.Client(base_url=args.base_url, timeout=60.0) as client:
        login(client)
        default_model = client.get("/api/info").json().get("model", "")
        everyone = finder(client, args.disease, "all")
        disease_label = everyone["display_name"]
        percentile_of = {row["individual_id"]: row["percentile"] for row in everyone["results"]}
        individuals = {
            "general": args.individual or pick_general_individual(client, args.disease),
            "rare": args.rare_individual or pick_rare_individual(client, args.disease),
        }
        payload = {
            "run": {
                "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "finished_at": None,
                "base_url": args.base_url,
                "questions_file": args.questions.name,
                "questions_sha256": hashlib.sha256(args.questions.expanduser().read_bytes()).hexdigest(),
                "portal_commit": portal_commit(),
                "default_model": default_model,
                "model_requested": args.model,
                "disease": args.disease,
                "disease_label": disease_label,
                "language": args.language,
                "individuals": individuals,
                "percentiles": {role: percentile_of.get(pid) for role, pid in individuals.items()},
                "selection": ("general: lowest ID without a panel finding for the disease; "
                              "rare: lowest ID with a panel alert and at least one other finding"
                              if not (args.individual or args.rare_individual) else "given on the command line"),
                "note": "The chat API does not report which model answered; a server-side fallback is not visible here.",
            },
            "sessions": [],
            "results": [],
        }

        order = 0
        for section in dict.fromkeys(q["section"] for q in questions):
            role = "rare" if section == RARE_SECTION else "general"
            base = {"individual_id": individuals[role], "disease": args.disease, "cohort": "kpredict",
                    "language": args.language, "model": args.model}
            started = time.monotonic()
            session = {"section": section, "individual_role": role, "status": "ok", "error": None}
            try:
                summary = run_task(client, "/api/summary/start", {**base, "gene_count": 5})
                session.update(summary_text=summary.get("summary", ""), session_id=summary.get("session_id"))
            except Exception as error:  # record and skip the section; the run continues
                session.update(status="failed", error=str(error), session_id=None, summary_text="")
            session["seconds"] = round(time.monotonic() - started, 1)
            payload["sessions"].append(session)
            print(f"[{section}] summary {session['status']} ({session['seconds']} s)", flush=True)

            for question in (q for q in questions if q["section"] == section):
                order += 1
                result = {
                    "order": order, "id": question["id"], "section": section, "topic": question["topic"],
                    "question": question["question"],
                    "asked": question["question"].replace("[disease]", disease_label.lower()),
                    "clinician_rating": question["rating"], "clinician_comment": question["comment"],
                    "individual_role": role, "status": "ok", "answer": "", "references": [], "error": None,
                }
                started = time.monotonic()
                if session["status"] != "ok":
                    result.update(status="skipped", error="section summary failed")
                else:
                    try:
                        answer = run_task(client, "/api/chat/start",
                                          {**base, "query": result["asked"], "session_id": session["session_id"]})
                        result.update(answer=answer.get("answer", ""), references=answer.get("references") or [])
                        session["session_id"] = answer.get("session_id") or session["session_id"]
                    except Exception as error:
                        result.update(status="failed", error=str(error))
                result["seconds"] = round(time.monotonic() - started, 1)
                payload["results"].append(result)
                score(payload, expectations)
                write_json(out, payload)
                print(f"  {question['id']}: {result['status']}, {'pass' if result['passed'] else 'FAIL'} "
                      f"({result['seconds']} s)", flush=True)
    payload["run"]["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return payload


def main() -> int:
    args = parse_args()
    expectations = load_expectations(args.expectations)
    if args.rescore:
        payload = json.loads(args.rescore.expanduser().read_text(encoding="utf-8"))
    else:
        if not args.questions:
            raise SystemExit("--questions is required unless --rescore is given")
        questions = select_questions(load_questions(args.questions.expanduser()), args.only)
        if args.dry_run:
            return dry_run(questions, expectations)
        if not args.out:
            raise SystemExit("--out is required for a run")
        payload = ask_all(args, questions, expectations)
    score(payload, expectations)
    out = (args.out or args.rescore).expanduser()
    write_json(out, payload)
    if args.markdown:
        write_markdown(args.markdown.expanduser(), payload)
    print_report(payload)
    if args.compare:
        print_comparison(payload, args.compare.expanduser())
    return exit_code(payload)


if __name__ == "__main__":
    sys.exit(main())
