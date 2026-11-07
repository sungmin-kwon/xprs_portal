#!/usr/bin/env python3
"""Run the small XPRS chatbot golden evaluation set.

The default mode validates the corpus and runs deterministic routing checks.
`--live` additionally sends the controlled, non-private generation cases through
the production follow-up prompt and configured generation model. Live results
still require the manual grounding review listed for each case.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_CASES = ROOT / "benchmarks" / "chatbot_quality_cases.json"
KNOWN_CATEGORIES = {
    "citation_grounding",
    "evidence_scarcity",
    "bilingual_output",
    "clinical_safety",
}
UNCERTAINTY_MARKERS = {
    "en": (
        "no evidence", "no citable", "not available", "not supplied", "insufficient",
        "no eligible", "no supporting evidence", "no specific published association",
        "cannot establish", "does not establish", "indirect", "unclear", "limited",
    ),
    "ko": (
        "근거가 없", "근거를 찾", "제공되지", "충분하지", "확립되지", "판단할 수 없",
        "간접", "불분명", "제한적",
    ),
}
NONCAUSAL_MARKERS = {
    "en": (
        "association", "associated", "does not prove", "does not establish",
        "cannot establish", "not caus", "not evidence", "model contribution", "model-relative",
        "statistical contribution", "relative to the reference cohort",
    ),
    "ko": (
        "연관", "인과관계가 확립되지", "인과관계를 입증", "원인임을 의미하지",
        "모델 내", "모델에서의 기여",
    ),
}


class RecordingLLM:
    """Expose raw model output/errors that production helpers intentionally hide."""

    def __init__(self, delegate):
        self.delegate = delegate
        self.model = getattr(delegate, "model", None)
        self.last_raw = ""
        self.last_error = ""

    def reset(self) -> None:
        self.last_raw = ""
        self.last_error = ""

    def chat(self, *args, **kwargs):
        self.reset()
        try:
            self.last_raw = self.delegate.chat(*args, **kwargs) or ""
            return self.last_raw
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            raise


def load_corpus(path: Path = DEFAULT_CASES) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_corpus(corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    cases = corpus.get("cases")
    if not isinstance(cases, list) or not cases:
        return ["Corpus must contain a non-empty cases array."]

    ids = [case.get("id") for case in cases]
    duplicates = [case_id for case_id, count in Counter(ids).items() if count > 1]
    if duplicates:
        errors.append(f"Duplicate case IDs: {', '.join(str(item) for item in duplicates)}")

    for index, case in enumerate(cases, start=1):
        label = case.get("id") or f"case #{index}"
        for field in ("id", "category", "mode", "language", "question", "expected"):
            if not case.get(field):
                errors.append(f"{label}: missing {field}")
        if case.get("category") not in KNOWN_CATEGORIES:
            errors.append(f"{label}: unknown category {case.get('category')!r}")
        if case.get("mode") not in {"generation", "routing"}:
            errors.append(f"{label}: invalid mode {case.get('mode')!r}")
        if case.get("language") not in {"en", "ko"}:
            errors.append(f"{label}: language must be en or ko")
        if case.get("mode") == "generation":
            for evidence in case.get("evidence") or []:
                if not evidence.get("n") or not evidence.get("context"):
                    errors.append(f"{label}: every evidence record needs n and context")
            allowed = set(case.get("expected", {}).get("allowed_citations") or [])
            supplied = {item.get("n") for item in case.get("evidence") or []}
            if not allowed.issubset(supplied):
                errors.append(f"{label}: allowed citations are not all present in evidence")

    pair_members: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        if case.get("pair_id"):
            pair_members[str(case["pair_id"])].append(case)
    for pair_id, members in pair_members.items():
        if len(members) != 2 or {item.get("language") for item in members} != {"en", "ko"}:
            errors.append(f"{pair_id}: bilingual pair must contain exactly one en and one ko case")
    return errors


def _citations(answer: str) -> set[int]:
    return {int(value) for value in re.findall(r"\[(\d+)\]", answer or "")}


def _contains_any(answer: str, markers: tuple[str, ...]) -> bool:
    lowered = (answer or "").lower()
    return any(marker.lower() in lowered for marker in markers)


def _canonical_token_text(value: str) -> str:
    # A typographic Unicode minus is numerically equivalent to ASCII '-'.
    return str(value).replace("−", "-").replace("﹣", "-")


def grade_case(case: dict[str, Any], *, answer: str = "", route: str | None = None) -> dict[str, Any]:
    expected = case.get("expected") or {}
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    if case.get("mode") == "routing":
        wanted = str(expected.get("route") or "")
        add("route", route == wanted, f"expected={wanted}; actual={route}")
        return {
            "automated_pass": all(item["passed"] for item in checks),
            "checks": checks,
            "manual_review_required": False,
        }

    lowered = answer.lower()
    canonical_lowered = _canonical_token_text(answer).lower()
    for term in expected.get("required_terms") or []:
        add(
            f"required:{term}",
            _canonical_token_text(term).lower() in canonical_lowered,
            f"Answer must contain {term!r}",
        )
    for term in expected.get("forbidden_terms") or []:
        add(f"forbidden:{term}", str(term).lower() not in lowered, f"Answer must not contain {term!r}")

    cited = _citations(answer)
    allowed = {int(value) for value in expected.get("allowed_citations") or []}
    add("citation-range", cited.issubset(allowed), f"allowed={sorted(allowed)}; used={sorted(cited)}")
    min_citations = int(expected.get("min_citations", 0))
    max_citations = int(expected.get("max_citations", len(allowed)))
    add(
        "citation-count",
        min_citations <= len(cited) <= max_citations,
        f"expected={min_citations}..{max_citations}; unique_used={len(cited)}",
    )

    language = case.get("language", "en")
    if language == "ko":
        add("output-language", bool(re.search(r"[가-힣]", answer)), "Korean output must contain Hangul")
    else:
        hangul_count = len(re.findall(r"[가-힣]", answer))
        add("output-language", hangul_count == 0, f"English output Hangul characters={hangul_count}")

    if expected.get("uncertainty_required"):
        add(
            "uncertainty",
            _contains_any(answer, UNCERTAINTY_MARKERS[language]),
            "Answer must explicitly qualify absent, limited, or indirect evidence",
        )
    if expected.get("noncausal_required"):
        add(
            "noncausal-framing",
            _contains_any(answer, NONCAUSAL_MARKERS[language]),
            "Answer must distinguish association/model contribution from causation",
        )
    for token in expected.get("preserve_tokens") or []:
        add(
            f"preserve:{token}",
            _canonical_token_text(token) in _canonical_token_text(answer),
            f"Answer must preserve {token!r} (typographic minus signs are equivalent)",
        )

    return {
        "automated_pass": all(item["passed"] for item in checks),
        "checks": checks,
        "manual_review_required": bool(expected.get("manual_review")),
        "manual_review": expected.get("manual_review") or [],
        "citations": sorted(cited),
    }


def _run_route(case: dict[str, Any]) -> str:
    from agents.conversation import ConversationAgent

    return ConversationAgent.classify_turn_fallback(
        case["question"],
        available_genes=["KCNQ1", "CDKAL1", "MOV10", "RHOC", "ESR1", "GML"],
    )


def _build_generation_agent(model: str | None = None):
    from agents.explanation import ExplanationAgent
    from llm_utils import LLM_PROVIDER, build_llm_agent, build_llm_client

    client, default_model = build_llm_client(LLM_PROVIDER)
    agent = ExplanationAgent.__new__(ExplanationAgent)
    agent.llm = RecordingLLM(
        build_llm_agent(LLM_PROVIDER, client=client, model=model or default_model)
    )
    return agent


def _run_generation(agent, case: dict[str, Any]) -> tuple[str, str, str]:
    evidence = case.get("evidence") or []
    compact_context = "\n".join(
        f"[{item['n']}] {item['title']}: {item['context']}"
        for item in evidence
    )
    reference_index = "\n".join(
        f"[{item['n']}] {item['title']}"
        for item in evidence
    )
    agent.disease_display_name = case.get("disease") or "Selected disease"
    agent.llm.reset()
    answer = agent._generate_followup_text(
        background=case.get("background") or "",
        compact_ctx=compact_context,
        ref_index=reference_index,
        question=case["question"],
        n_max=len(evidence),
        language=case.get("language") or "en",
    )
    return answer, agent.llm.last_raw, agent.llm.last_error


def evaluate(corpus: dict[str, Any], *, live: bool = False, model: str | None = None) -> dict[str, Any]:
    errors = validate_corpus(corpus)
    if errors:
        raise ValueError("\n".join(errors))

    generation_agent = _build_generation_agent(model) if live else None
    results: list[dict[str, Any]] = []
    for case in corpus["cases"]:
        route = _run_route(case) if case["mode"] == "routing" else None
        raw_model_output = ""
        generation_error = ""
        if live and case["mode"] == "generation":
            answer, raw_model_output, generation_error = _run_generation(generation_agent, case)
        else:
            answer = ""
        grade = (
            grade_case(case, answer=answer, route=route)
            if case["mode"] == "routing" or live
            else {"automated_pass": None, "checks": [], "manual_review_required": True, "manual_review": case["expected"].get("manual_review") or []}
        )
        results.append({
            "id": case["id"],
            "category": case["category"],
            "mode": case["mode"],
            "language": case["language"],
            "question": case["question"],
            "route": route,
            "answer": answer,
            "raw_model_output": raw_model_output,
            "generation_error": generation_error,
            **grade,
        })

    by_category: dict[str, dict[str, int]] = {}
    for category in KNOWN_CATEGORIES:
        selected = [item for item in results if item["category"] == category]
        by_category[category] = {
            "total": len(selected),
            "run": sum(item["automated_pass"] is not None for item in selected),
            "passed": sum(item["automated_pass"] is True for item in selected),
            "failed": sum(item["automated_pass"] is False for item in selected),
            "generation_errors": sum(bool(item.get("generation_error")) for item in selected),
            "manual_pending": sum(bool(item.get("manual_review_required")) for item in selected),
        }

    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_version": corpus.get("version"),
        "live_generation": live,
        "model": getattr(getattr(generation_agent, "llm", None), "model", None),
        "summary": by_category,
        "results": results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# XPRS chatbot quality evaluation",
        "",
        f"- Evaluated: {report['evaluated_at']}",
        f"- Live generation: {report['live_generation']}",
        f"- Model: {report.get('model') or 'not invoked'}",
        "",
        "## Automated summary",
        "",
        "| Category | Run | Passed | Failed | Generation errors | Manual review pending |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for category in sorted(report["summary"]):
        item = report["summary"][category]
        lines.append(
            f"| {category.replace('_', ' ').title()} | {item['run']}/{item['total']} | "
            f"{item['passed']} | {item['failed']} | {item['generation_errors']} | {item['manual_pending']} |"
        )

    for result in report["results"]:
        lines.extend(["", f"## {result['id']}", "", f"**Prompt:** {result['question']}"])
        if result.get("route"):
            lines.append(f"\n**Route:** `{result['route']}`")
        if result.get("answer"):
            lines.extend(["", "**Answer:**", "", result["answer"]])
        elif result.get("generation_error"):
            lines.append(f"\n**Generation error:** `{result['generation_error']}`")
        elif result.get("raw_model_output"):
            lines.extend(["", "**Unparsed model output:**", "", "```text", result["raw_model_output"], "```"])
        failed = [item for item in result.get("checks") or [] if not item["passed"]]
        if result.get("automated_pass") is not None:
            lines.append(f"\n**Automated result:** {'PASS' if result['automated_pass'] else 'FAIL'}")
        if failed:
            lines.extend(["", "Failed checks:"])
            lines.extend(f"- {item['name']}: {item['detail']}" for item in failed)
        if result.get("manual_review"):
            lines.extend(["", "Manual review:"])
            lines.extend(f"- [ ] {item}" for item in result["manual_review"])
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--live", action="store_true", help="Run controlled generation cases through the configured model")
    parser.add_argument("--model", help="Optional configured model ID for live generation")
    parser.add_argument("--case", action="append", dest="case_ids", help="Run only this case ID (repeatable)")
    parser.add_argument("--output", type=Path, help="Write JSON results and a sibling Markdown report")
    args = parser.parse_args()

    corpus = load_corpus(args.cases)
    if args.case_ids:
        selected = set(args.case_ids)
        unknown = selected - {case.get("id") for case in corpus.get("cases") or []}
        if unknown:
            parser.error(f"Unknown case ID(s): {', '.join(sorted(unknown))}")
        corpus = {**corpus, "cases": [case for case in corpus["cases"] if case.get("id") in selected]}
    report = evaluate(corpus, live=args.live, model=args.model)
    for category in sorted(report["summary"]):
        item = report["summary"][category]
        print(
            f"{category}: run={item['run']}/{item['total']} "
            f"passed={item['passed']} failed={item['failed']} "
            f"generation_errors={item['generation_errors']} manual_pending={item['manual_pending']}"
        )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        markdown_path = args.output.with_suffix(".md")
        markdown_path.write_text(render_markdown(report), encoding="utf-8")
        print(f"JSON: {args.output}")
        print(f"Markdown: {markdown_path}")

    return 1 if any(item["failed"] for item in report["summary"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
