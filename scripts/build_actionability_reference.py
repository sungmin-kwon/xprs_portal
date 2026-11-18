#!/usr/bin/env python3
"""Build the portal's ClinGen Actionability reference file from downloaded reports.

Input (``--reference-dir``, outside the repository):
- ``adult_flat.tsv``: the flat adult summary (one row per outcome-intervention pair),
  from https://actionability.clinicalgenome.org/ac/Adult/api/summ?flavor=flat
- ``adult_reports/<docId>.json``: the detailed report for each released report, from
  https://actionability.clinicalgenome.org/ac/Adult/api/sepio/doc/<docId>
  (needed for the modes of inheritance, which the summary lacks)

Output: ``portal_actionability.json`` in the same folder, read by ``actionability.py``.

Only released gene-condition reports in the adult context are kept. The
structured modeOfInheritance field can list a single mode although the report's
"Modes of Inheritance" section lists several (e.g. hypertrophic cardiomyopathy),
so every statement in that section is collected.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

INHERITANCE_TERMS = re.compile(r"autosomal dominant|autosomal recessive|x-linked|semidominant|mitochondrial", re.I)
REPORT_URL = "https://actionability.clinicalgenome.org/ac/Adult/ui/stg2SummaryRpt?doc={doc_id}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reference-dir", type=Path, required=True)
    return parser.parse_args()


def modes_of_inheritance(report: dict) -> list[str]:
    """All inheritance modes stated in a detailed report's 'Modes of Inheritance' section."""
    found: set[str] = set()

    def walk(obj) -> None:
        if isinstance(obj, dict):
            if "Modes of Inheritance" in str(obj.get("evidenceDomainTag", "")):
                found.update(m.lower() for m in INHERITANCE_TERMS.findall(str(obj.get("narrative", ""))))
            mode = obj.get("modeOfInheritance")
            if isinstance(mode, dict) and mode.get("keyText"):
                found.update(m.lower() for m in INHERITANCE_TERMS.findall(mode["keyText"]))
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(report)
    return sorted(found)


def build(reference_dir: Path) -> dict:
    flat = pd.read_csv(reference_dir / "adult_flat.tsv", sep="\t", dtype=str).fillna("")
    flat = flat[(flat["status-overall"] == "Released") & (flat["curationType"] == "Gene-Condition")]
    reports = []
    missing = []
    for doc_id, rows in flat.groupby("docId", sort=True):
        detail_path = reference_dir / "adult_reports" / f"{doc_id}.json"
        if not detail_path.is_file():
            missing.append(doc_id)
            continue
        first = rows.iloc[0]
        genes = sorted({g.strip() for value in rows["geneOrVariant"] for g in value.split(",") if g.strip()})
        outcomes = [
            {
                "outcome": row["outcome"],
                "intervention": row["intervention"],
                "severity": row["severity"],
                "likelihood": row["likelihood"],
                "nature_of_intervention": row["natureOfIntervention"],
                "effectiveness": row["effectiveness"],
                "overall": row["overall"],
            }
            for _, row in rows.iterrows()
        ]
        reports.append({
            "doc_id": doc_id,
            "context": "Adult",
            "condition": first["disease"],
            "genes": genes,
            "inheritance": modes_of_inheritance(json.loads(detail_path.read_text(encoding="utf-8"))),
            "release": first["release"],
            "release_date": first["releaseDate"],
            "outcomes": outcomes,
            "url": REPORT_URL.format(doc_id=doc_id),
        })
    if missing:
        raise SystemExit(f"Detailed reports missing for {len(missing)} released reports, e.g. {missing[:5]}")
    return {
        "source": "ClinGen Actionability Knowledge Repository (adult context, released gene-condition reports)",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "report_count": len(reports),
        "reports": reports,
    }


def main() -> int:
    args = parse_args()
    reference_dir = args.reference_dir.expanduser().resolve()
    payload = build(reference_dir)
    out = reference_dir / "portal_actionability.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    genes = {gene for report in payload["reports"] for gene in report["genes"]}
    print(f"wrote {out.name}: {payload['report_count']} reports, {len(genes)} genes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
