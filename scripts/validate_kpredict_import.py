#!/usr/bin/env python3
"""Validate a derived K-PREDICT release without printing participant IDs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd


PSEUDONYM_RE = re.compile(r"^KP-[A-F0-9]{12}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_score_folder(parent: Path, entry: dict, slug_key: str, pseudonyms: set[str], errors: list[str]) -> None:
    """Check one diseases/<slug> or traits/<slug> folder against its manifest entry."""
    slug = str(entry.get(slug_key) or "")
    folder = parent / slug
    risk = pd.read_parquet(folder / "individual_risk.parquet")
    genes = pd.read_parquet(folder / "genes.parquet")
    matrix = json.loads((folder / "matrix.json").read_text(encoding="utf-8"))
    if set(risk["individual_id"].astype(str)) != pseudonyms:
        errors.append(f"{slug}: pseudonymous individual set differs from the cohort mapping")
    if len(risk) != int(entry.get("individual_count") or -1):
        errors.append(f"{slug}: individual count differs from the manifest")
    if len(genes) != int(entry.get("gene_count") or -1):
        errors.append(f"{slug}: gene count differs from the manifest")
    shape = [int(value) for value in matrix.get("shape", [])]
    if shape != [len(genes), len(risk)]:
        errors.append(f"{slug}: contribution matrix shape metadata is invalid")
    binary_path = folder / str(matrix.get("data_file"))
    if binary_path.stat().st_size != len(genes) * len(risk) * 4:
        errors.append(f"{slug}: contribution matrix byte size is invalid")
    if int(risk["applicable"].sum()) != int(entry.get("applicable_count") or -1):
        errors.append(f"{slug}: applicable count differs from the manifest")
    for filename, details in (entry.get("files") or {}).items():
        path = folder / filename
        if not path.is_file() or path.stat().st_size != int(details.get("bytes") or -1):
            errors.append(f"{slug}: {filename} is missing or has the wrong size")
            continue
        if sha256_file(path) != details.get("sha256"):
            errors.append(f"{slug}: {filename} checksum mismatch")


def validate_release(root: Path) -> list[str]:
    errors: list[str] = []
    root = root.expanduser().resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return ["manifest.json is missing"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("cohort_slug") != "kpredict" or manifest.get("cohort_label") != "K-PREDICT":
        errors.append("cohort identity is not K-PREDICT")
    if manifest.get("private_data") is not True or manifest.get("source_paths_recorded") is not False:
        errors.append("manifest privacy flags are invalid")

    for directory, subdirectories, filenames in os.walk(root):
        if Path(directory).stat().st_mode & 0o777 != 0o700:
            errors.append("one or more release directories are not mode 0700")
            break
        for name in subdirectories:
            if (Path(directory) / name).stat().st_mode & 0o777 != 0o700:
                errors.append("one or more release directories are not mode 0700")
                break
        for name in filenames:
            if (Path(directory) / name).stat().st_mode & 0o777 != 0o600:
                errors.append("one or more release files are not mode 0600")
                break

    mapping = pd.read_parquet(root / "_restricted" / "id_map.parquet")
    if mapping["source_iid"].duplicated().any() or mapping["pseudonym"].duplicated().any():
        errors.append("restricted IID mapping is not one-to-one")
    pseudonyms = set(mapping["pseudonym"].astype(str))
    if not pseudonyms or not all(PSEUDONYM_RE.fullmatch(value) for value in pseudonyms):
        errors.append("browser-facing pseudonyms do not match the expected format")
    if len(pseudonyms) != int(manifest.get("individual_count") or -1):
        errors.append("manifest individual count differs from the restricted mapping")

    for disease in manifest.get("diseases", []):
        check_score_folder(root / "diseases", disease, "portal_disease_slug", pseudonyms, errors)
    # Continuous traits (from 2026-11-19) use the same per-folder layout.
    for trait in manifest.get("traits") or []:
        check_score_folder(root / "traits", trait, "portal_trait_slug", pseudonyms, errors)
        slug = trait.get("portal_trait_slug")
        if not str(trait.get("reference_cohort") or "").strip():
            errors.append(f"{slug}: reference_cohort is not recorded in the manifest")
        risk = pd.read_parquet(root / "traits" / str(slug) / "individual_risk.parquet")
        percentiles = risk["percentile"].dropna()
        if percentiles.empty or percentiles.min() < 0 or percentiles.max() > 100:
            errors.append(f"{slug}: percentiles are missing or outside 0–100")

    findings = pd.read_parquet(root / "rare_findings.parquet")
    finding_index = pd.read_parquet(root / "rare_finding_index.parquet")
    if not set(findings["individual_id"].astype(str)).issubset(pseudonyms):
        errors.append("rare findings contain an unknown pseudonymous individual")
    if findings["finding_id"].duplicated().any():
        errors.append("rare finding IDs are not unique")
    rare_manifest = manifest.get("rare_findings") or {}
    if len(findings) != int(rare_manifest.get("finding_count") or -1):
        errors.append("rare finding count differs from the manifest")
    if int(finding_index["finding_count"].sum()) != len(findings):
        errors.append("rare finding index does not reproduce the finding count")
    if int(finding_index["alert_count"].sum()) != int(findings["moi_call"].eq("alert").sum()):
        errors.append("rare finding index does not reproduce the alert count")
    # Content checks: the 2026-09-17 release passed every structural check while
    # gnomad_af_eas was NaN in all rows (percent strings coerced to NaN).
    for column in ("gnomad_af", "gnomad_af_eas", "cohort_af"):
        if column not in findings:
            continue
        values = pd.to_numeric(findings[column], errors="coerce")
        if values.notna().sum() == 0:
            errors.append(f"rare findings: {column} has no values (all missing)")
        elif ((values < 0) | (values > 1)).any():
            errors.append(f"rare findings: {column} has values outside 0–1 (expected allele fractions)")
    for entry in manifest.get("diseases") or []:
        if not str(entry.get("reference_cohort") or "").strip():
            errors.append(f"{entry.get('portal_disease_slug')}: reference_cohort is not recorded in the manifest")
    for filename, details in (rare_manifest.get("files") or {}).items():
        path = root / filename
        if not path.is_file() or path.stat().st_size != int(details.get("bytes") or -1):
            errors.append(f"{filename} is missing or has the wrong size")
            continue
        if sha256_file(path) != details.get("sha256"):
            errors.append(f"{filename} checksum mismatch")
    return errors


def main() -> int:
    args = parse_args()
    try:
        errors = validate_release(args.release_dir)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Validation could not complete: {exc}", file=sys.stderr)
        return 2
    if errors:
        print(f"K-PREDICT release validation failed ({len(errors)} errors):")
        for error in errors:
            print(f"  ERROR: {error}")
        return 1
    print("K-PREDICT release validation passed.")
    print("Checksums, permissions, pseudonyms, matrix dimensions, and rare-finding indexes are consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
