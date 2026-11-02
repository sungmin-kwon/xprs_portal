#!/usr/bin/env python3
"""Recalculate provider-cache eligibility metadata without network requests.

Run without --write for a dry run. The write mode only updates the stored
``eligible_count`` field; paper records and provider pagination checkpoints are
preserved.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any


REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_DIR / ".env")

from config import EUROPE_PMC_CACHE_DIR, S2_CACHE_DIR  # noqa: E402
from reference_utils import literature_paper_is_eligible  # noqa: E402


def _read_payload(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("top-level JSON value is not an object")
    return value


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Atomically update changed eligible_count values.",
    )
    args = parser.parse_args()

    providers = (
        ("Europe PMC", EUROPE_PMC_CACHE_DIR, "*_epmc.json"),
        ("Semantic Scholar", S2_CACHE_DIR, "*_s2.json"),
    )
    inspected = 0
    changed = 0
    invalid = 0

    for provider, directory, pattern in providers:
        for path in sorted(directory.glob(pattern)):
            inspected += 1
            try:
                payload = _read_payload(path)
                gene = str(payload.get("gene") or "").strip().upper()
                if not gene:
                    raise ValueError("gene is missing")
                papers = [
                    paper for paper in payload.get("data", [])
                    if isinstance(paper, dict)
                ]
                eligible = sum(
                    literature_paper_is_eligible(paper, gene) for paper in papers
                )
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                invalid += 1
                print(f"[invalid] {path}: {error}")
                continue

            previous = payload.get("eligible_count")
            if previous == eligible:
                continue
            changed += 1
            action = "updated" if args.write else "would update"
            print(
                f"[{action}] {provider}: {path.name}: "
                f"eligible_count {previous!r} -> {eligible}"
            )
            if args.write:
                payload["eligible_count"] = eligible
                _write_payload(path, payload)

    mode = "write" if args.write else "dry run"
    print(
        f"{mode}: inspected={inspected}, changed={changed}, invalid={invalid}"
    )
    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())
