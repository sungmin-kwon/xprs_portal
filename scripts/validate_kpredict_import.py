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
        slug = str(disease.get("portal_disease_slug") or "")
        disease_dir = root / "diseases" / slug
        risk = pd.read_parquet(disease_dir / "individual_risk.parquet")
        genes = pd.read_parquet(disease_dir / "genes.parquet")
        matrix = json.loads((disease_dir / "matrix.json").read_text(encoding="utf-8"))
        if set(risk["individual_id"].astype(str)) != pseudonyms:
            errors.append(f"{slug}: pseudonymous individual set differs from the cohort mapping")
        if len(risk) != int(disease.get("individual_count") or -1):
            errors.append(f"{slug}: individual count differs from the manifest")
        if len(genes) != int(disease.get("gene_count") or -1):
            errors.append(f"{slug}: gene count differs from the manifest")
        shape = [int(value) for value in matrix.get("shape", [])]
        if shape != [len(genes), len(risk)]:
            errors.append(f"{slug}: contribution matrix shape metadata is invalid")
        binary_path = disease_dir / str(matrix.get("data_file"))
        if binary_path.stat().st_size != len(genes) * len(risk) * 4:
            errors.append(f"{slug}: contribution matrix byte size is invalid")
        if int(risk["applicable"].sum()) != int(disease.get("applicable_count") or -1):
            errors.append(f"{slug}: applicable count differs from the manifest")
        for filename, details in (disease.get("files") or {}).items():
            path = disease_dir / filename
            if not path.is_file() or path.stat().st_size != int(details.get("bytes") or -1):
                errors.append(f"{slug}: {filename} is missing or has the wrong size")
                continue
            if sha256_file(path) != details.get("sha256"):
                errors.append(f"{slug}: {filename} checksum mismatch")

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
