"""ClinGen Actionability references for rare-variant findings.

A report is attached to a finding only when it plausibly applies:
- the finding's gene is one of the report's genes;
- the report's condition shares disease terms with the finding's ClinVar
  conditions (generic words such as "hereditary", "syndrome" or "cancer" are
  ignored), so e.g. a BRCA2 finding annotated for breast/ovarian cancer is not
  linked to the Fanconi anemia report;
- the report's inheritance makes a single variant relevant (dominant,
  semidominant or X-linked), or the report is recessive and the finding is
  homozygous. Reports without a stated inheritance are not attached.

This is a text heuristic over public data (see
xprs_reports/2026-11-18_clingen_actionability_check.md). Matches are shown as
references, never as recommendations for an individual.

The reference file is built by scripts/build_actionability_reference.py; its
path comes from ACTIONABILITY_REFERENCE_PATH. Without it the feature is off.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

GENERIC_TERMS = {
    "hereditary", "familial", "syndrome", "disease", "disorder", "type", "and", "the", "with", "of", "or", "to", "due",
    "autosomal", "dominant", "recessive", "susceptibility", "predisposition", "group", "complementation", "not",
    "provided", "specified", "related", "deficiency", "inborn", "genetic", "condition", "conditions", "cancer",
    "neoplasm",
}
SINGLE_COPY_MODES = ("autosomal dominant", "semidominant", "x-linked")


def _terms(text: object) -> set[str]:
    return {t for t in re.findall(r"[a-z][a-z0-9]{3,}", str(text or "").lower()) if t not in GENERIC_TERMS}


@lru_cache(maxsize=2)
def _reports_by_gene(path_string: str) -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(Path(path_string).read_text(encoding="utf-8"))
    by_gene: dict[str, list[dict[str, Any]]] = {}
    for report in payload.get("reports") or []:
        for gene in report.get("genes") or []:
            by_gene.setdefault(gene, []).append(report)
    return by_gene


def reference_path() -> Path | None:
    configured = os.getenv("ACTIONABILITY_REFERENCE_PATH", "").strip()
    if not configured:
        return None
    path = Path(configured).expanduser()
    return path if path.is_file() else None


def _outcomes_for_gene(report: dict[str, Any], gene: str) -> list[dict[str, Any]]:
    """Rows of a multi-gene report that concern this gene.

    Multi-gene reports label rows with the gene, e.g. "Breast Cancer (ATM)" and
    "Breast cancer (CHEK2)"; an ATM finding should not list the CHEK2 rows.
    Reports without such labels apply to all their genes.
    """
    outcomes = report.get("outcomes") or []
    tagged = [o for o in outcomes if re.search(r"\(([A-Z0-9-]+(?:\s*,\s*[A-Z0-9-]+)*)\)\s*$", str(o.get("outcome") or ""))]
    if not tagged:
        return outcomes
    own = [o for o in outcomes if re.search(rf"\(([^)]*\b{re.escape(gene)}\b[^)]*)\)\s*$", str(o.get("outcome") or ""))]
    return own or outcomes


def _summary(report: dict[str, Any], gene: str) -> dict[str, Any]:
    outcomes = _outcomes_for_gene(report, gene)
    interventions = []
    for outcome in outcomes:
        label = str(outcome.get("intervention") or "").strip()
        if label and label not in interventions:
            interventions.append(label)
    return {
        "doc_id": report.get("doc_id"),
        "context": report.get("context"),
        "condition": report.get("condition"),
        "inheritance": report.get("inheritance") or [],
        "interventions": interventions,
        "outcomes": outcomes,
        "url": report.get("url"),
    }


def matching_reports(finding: dict[str, Any], path: Path | None = None) -> list[dict[str, Any]]:
    """Actionability reports that plausibly apply to one rare-variant finding (may be empty)."""
    path = path or reference_path()
    if path is None:
        return []
    by_gene = _reports_by_gene(str(path))
    genes = [g for g in re.split(r"\s*,\s*", str(finding.get("gene") or "")) if g]
    finding_terms = set()
    for condition in str(finding.get("clinvar_conditions") or "").split(";"):
        finding_terms |= _terms(condition)
    homozygous = str(finding.get("genotype") or "") in {"1/1", "1|1"}
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for gene in genes:
        for report in by_gene.get(gene, []):
            if report.get("doc_id") in seen:
                continue
            modes = report.get("inheritance") or []
            single_copy = any(mode in SINGLE_COPY_MODES for mode in modes)
            recessive = "autosomal recessive" in modes
            if not (single_copy or (recessive and homozygous)):
                continue
            if not (_terms(report.get("condition")) & finding_terms):
                continue
            seen.add(report.get("doc_id"))
            matches.append(_summary(report, gene))
    return matches
