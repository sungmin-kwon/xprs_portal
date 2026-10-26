#!/usr/bin/env python3
"""Audit the private K-PREDICT handoff without emitting participant IDs.

The command is read-only. It validates aggregate rare-variant counts and the
structural contract of each disease RDS. Optional JSON output must be written
outside the public repository and is created with mode 0600.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kpredict_schema import SOURCE_DISEASE_TO_PORTAL


EXPECTED_DISEASES = {
    source_id: {"portal_slug": portal_slug}
    for source_id, portal_slug in SOURCE_DISEASE_TO_PORTAL.items()
}
EXPECTED_RARE_COLUMNS = (
    "IID",
    "track",
    "xprs_disease",
    "xprs_disease_label",
    "gene",
    "variant",
    "hgvs",
    "rsid",
    "genotype",
    "moi_call",
    "moi_why",
    "panelapp_moi",
    "panelapp_n_panels",
    "clingen_moi",
    "clingen_tier",
    "clingen_detail",
    "clnsig",
    "clnsig_raw",
    "stars",
    "tier",
    "category",
    "consequence",
    "consequence_class",
    "clinvar_conditions",
    "gnomad_af",
    "gnomad_af_eas",
    "eas_specific",
    "cohort_af",
    "qc_pass",
    "qc_flags",
)
R_AUDIT_SCRIPT = r'''
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 3) {
  stop("Expected: <rds_dir> <rare_tsv> <output_tsv>", call. = FALSE)
}
rds_dir <- args[[1]]
rare_tsv <- args[[2]]
output_tsv <- args[[3]]

rare_header <- read.delim(
  rare_tsv,
  sep = "\t",
  header = TRUE,
  stringsAsFactors = FALSE,
  check.names = FALSE,
  colClasses = "character"
)
rare_iids <- unique(as.character(rare_header$IID))

scalar_text <- function(value) {
  if (is.null(value) || length(value) == 0 || is.na(value[[1]])) return("")
  as.character(value[[1]])
}

finite_max_error <- function(observed, expected) {
  observed <- as.numeric(observed)
  expected <- as.numeric(expected)
  keep <- is.finite(observed) & is.finite(expected)
  if (!any(keep)) return(NA_real_)
  max(abs(observed[keep] - expected[keep]))
}

files <- sort(list.files(rds_dir, pattern = "_cohort\\.[Rr][Dd][Ss]$", full.names = TRUE))
rows <- list()

for (path in files) {
  source_filename <- basename(path)
  source_stem <- sub("_cohort\\.[Rr][Dd][Ss]$", "", source_filename)
  d <- readRDS(path)
  required <- c("disease_id", "annotated_info", "full_prs", "PRS_info", "z", "pct", "ref_mean", "ref_sd")
  missing_objects <- setdiff(required, names(d))

  if (length(missing_objects) > 0) {
    rows[[length(rows) + 1]] <- data.frame(
      source_filename = source_filename,
      source_stem = source_stem,
      disease_id = scalar_text(d$disease_id),
      disease_label = scalar_text(d$disease_label),
      missing_objects = paste(missing_objects, collapse = "|"),
      stringsAsFactors = FALSE
    )
    rm(d)
    gc(verbose = FALSE)
    next
  }

  full_iids <- as.character(d$full_prs$IID)
  prs_iids <- names(d$PRS_info)
  raw_prs <- as.numeric(d$full_prs$PRS)
  expected_z <- (raw_prs - as.numeric(d$ref_mean[[1]])) / as.numeric(d$ref_sd[[1]])
  pct_numeric <- as.numeric(d$pct)
  finite_pct <- pct_numeric[is.finite(pct_numeric)]
  variance_numeric <- if ("variance" %in% names(d$annotated_info)) {
    as.numeric(d$annotated_info$variance)
  } else {
    numeric(0)
  }
  rank_one_rows <- if ("within_region_rank_by_variance" %in% names(d$annotated_info)) {
    sum(as.numeric(d$annotated_info$within_region_rank_by_variance) == 1, na.rm = TRUE)
  } else {
    NA_integer_
  }

  rows[[length(rows) + 1]] <- data.frame(
    source_filename = source_filename,
    source_stem = source_stem,
    disease_id = scalar_text(d$disease_id),
    disease_label = scalar_text(d$disease_label),
    missing_objects = "",
    object_names = paste(names(d), collapse = "|"),
    annotated_columns = paste(names(d$annotated_info), collapse = "|"),
    prs_rows = nrow(d$PRS_info),
    prs_columns = ncol(d$PRS_info),
    annotated_rows = nrow(d$annotated_info),
    full_prs_rows = nrow(d$full_prs),
    full_prs_unique_iids = length(unique(full_iids)),
    prs_unique_iids = length(unique(prs_iids)),
    duplicate_full_prs_iids = sum(duplicated(full_iids)),
    duplicate_prs_iids = sum(duplicated(prs_iids)),
    row_alignment = nrow(d$PRS_info) == nrow(d$annotated_info),
    iid_set_alignment = setequal(full_iids, prs_iids),
    rare_iids_missing_from_rds = length(setdiff(rare_iids, full_iids)),
    rds_iids_without_rare_findings = length(setdiff(full_iids, rare_iids)),
    z_length = length(d$z),
    z_non_missing = sum(is.finite(as.numeric(d$z))),
    pct_length = length(d$pct),
    pct_non_missing = sum(is.finite(pct_numeric)),
    pct_min = if (length(finite_pct)) min(finite_pct) else NA_real_,
    pct_max = if (length(finite_pct)) max(finite_pct) else NA_real_,
    ref_mean = as.numeric(d$ref_mean[[1]]),
    ref_sd = as.numeric(d$ref_sd[[1]]),
    z_formula_max_abs_error = finite_max_error(d$z, expected_z),
    variance_non_missing = sum(is.finite(variance_numeric)),
    rank_one_rows = rank_one_rows,
    stringsAsFactors = FALSE
  )
  rm(d)
  gc(verbose = FALSE)
}

all_names <- unique(unlist(lapply(rows, names)))
rows <- lapply(rows, function(row) {
  missing_names <- setdiff(all_names, names(row))
  for (name in missing_names) row[[name]] <- NA
  row[all_names]
})
result <- do.call(rbind, rows)
write.table(result, output_tsv, sep = "\t", row.names = FALSE, quote = TRUE, na = "")
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rds-dir", type=Path, required=True)
    parser.add_argument("--rare-tsv", type=Path, required=True)
    parser.add_argument(
        "--handoff-id",
        default="private-cohort-handoff",
        help="Non-identifying label stored in the aggregate manifest.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional aggregate-only JSON manifest; must be outside the repository.",
    )
    parser.add_argument(
        "--hash-files",
        action="store_true",
        help="Compute SHA-256 checksums for all source files (reads roughly 9.4 GB).",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarize_rare_findings(path: Path) -> tuple[dict[str, Any], list[str]]:
    data = pd.read_csv(path, sep="\t", dtype=str)
    missing_columns = [column for column in EXPECTED_RARE_COLUMNS if column not in data.columns]
    unexpected_columns = [column for column in data.columns if column not in EXPECTED_RARE_COLUMNS]

    alerts = data["moi_call"].eq("alert") if "moi_call" in data else pd.Series(False, index=data.index)
    carriers = data["moi_call"].eq("carrier") if "moi_call" in data else pd.Series(False, index=data.index)
    panel = data["track"].eq("panel") if "track" in data else pd.Series(False, index=data.index)
    other = data["track"].eq("other") if "track" in data else pd.Series(False, index=data.index)
    alert_iids = set(data.loc[alerts, "IID"]) if "IID" in data else set()
    carrier_iids = set(data.loc[carriers, "IID"]) if "IID" in data else set()
    key_columns = ["IID", "variant", "gene", "xprs_disease"]

    summary: dict[str, Any] = {
        "filename": path.name,
        "bytes": path.stat().st_size,
        "rows": int(len(data)),
        "columns": [str(column) for column in data.columns],
        "missing_columns": missing_columns,
        "unexpected_columns": unexpected_columns,
        "finding_iids": int(data["IID"].nunique()) if "IID" in data else 0,
        "alert_rows": int(alerts.sum()),
        "carrier_rows": int(carriers.sum()),
        "alert_iids": len(alert_iids),
        "carrier_only_iids": len(carrier_iids - alert_iids),
        "panel_rows": int(panel.sum()),
        "other_rows": int(other.sum()),
        "panel_alert_rows": int((panel & alerts).sum()),
        "other_alert_rows": int((other & alerts).sum()),
        "unique_variants": int(data["variant"].nunique()) if "variant" in data else 0,
        "unique_genes": int(data["gene"].nunique()) if "gene" in data else 0,
        "duplicate_key_rows": (
            int(data.duplicated(key_columns, keep=False).sum())
            if all(column in data for column in key_columns)
            else None
        ),
        "qc_pass_counts": (
            {str(key): int(value) for key, value in data["qc_pass"].value_counts(dropna=False).items()}
            if "qc_pass" in data
            else {}
        ),
        "panel_rows_by_disease": (
            {
                str(key): int(value)
                for key, value in data.loc[panel, "xprs_disease"].value_counts(dropna=False).sort_index().items()
            }
            if "xprs_disease" in data
            else {}
        ),
    }
    errors: list[str] = []
    if missing_columns:
        errors.append("Rare-variant TSV is missing required columns: " + ", ".join(missing_columns))
    if unexpected_columns:
        errors.append("Rare-variant TSV has unexpected columns: " + ", ".join(unexpected_columns))
    if summary["duplicate_key_rows"]:
        errors.append(f"Rare-variant composite key has {summary['duplicate_key_rows']} duplicate rows")
    if summary["qc_pass_counts"] != {"True": summary["rows"]}:
        errors.append("Not every rare-variant row has qc_pass=True")
    if summary["alert_rows"] + summary["carrier_rows"] != summary["rows"]:
        errors.append("Rare-variant moi_call values are not limited to alert/carrier")
    if summary["panel_rows"] + summary["other_rows"] != summary["rows"]:
        errors.append("Rare-variant track values are not limited to panel/other")
    if summary["panel_alert_rows"] + summary["other_alert_rows"] != summary["alert_rows"]:
        errors.append("Rare-variant alert track subtotals do not match the alert total")
    return summary, errors


def _bool_value(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def validate_rds_audit(frame: pd.DataFrame) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    observed_stems = set(frame.get("source_stem", pd.Series(dtype=str)).dropna().astype(str))
    expected_stems = set(EXPECTED_DISEASES)
    if observed_stems != expected_stems:
        errors.append(
            "RDS disease file set differs from the expected handoff "
            f"(missing={sorted(expected_stems - observed_stems)}, extra={sorted(observed_stems - expected_stems)})"
        )

    sample_counts = {
        int(value)
        for value in frame.get("prs_columns", pd.Series(dtype=float)).dropna()
    }
    cohort_sample_count = next(iter(sample_counts)) if len(sample_counts) == 1 else None
    if cohort_sample_count is None:
        errors.append(f"RDS files do not share one cohort sample count: {sorted(sample_counts)}")

    for row in frame.to_dict(orient="records"):
        stem = str(row.get("source_stem") or "")
        record = {
            str(key): (None if pd.isna(value) else value)
            for key, value in row.items()
        }
        if stem in EXPECTED_DISEASES:
            record["portal_slug"] = EXPECTED_DISEASES[stem]["portal_slug"]
        records.append(record)

        prefix = f"{stem or record.get('source_filename', 'unknown')}:"
        if record.get("missing_objects"):
            errors.append(f"{prefix} missing RDS objects: {record['missing_objects']}")
            continue
        expected = EXPECTED_DISEASES.get(stem)
        if not expected:
            continue
        integer_expectations = {
            "prs_columns": cohort_sample_count,
            "full_prs_rows": cohort_sample_count,
            "full_prs_unique_iids": cohort_sample_count,
            "prs_unique_iids": cohort_sample_count,
            "z_length": cohort_sample_count,
            "pct_length": cohort_sample_count,
            "rare_iids_missing_from_rds": 0,
        }
        for field, expected_value in integer_expectations.items():
            try:
                observed = int(record.get(field))
            except (TypeError, ValueError):
                observed = None
            if observed != expected_value:
                errors.append(f"{prefix} {field} expected {expected_value}, found {record.get(field)}")
        try:
            z_non_missing = int(record.get("z_non_missing"))
            pct_non_missing = int(record.get("pct_non_missing"))
        except (TypeError, ValueError):
            z_non_missing = pct_non_missing = -1
        if z_non_missing != pct_non_missing or not (0 < pct_non_missing <= int(cohort_sample_count or 0)):
            errors.append(f"{prefix} z/pct applicability counts are inconsistent")
        if stem != str(record.get("disease_id") or ""):
            errors.append(f"{prefix} disease_id does not match its filename")
        if not _bool_value(record.get("row_alignment")):
            errors.append(f"{prefix} PRS_info and annotated_info row counts differ")
        if not _bool_value(record.get("iid_set_alignment")):
            errors.append(f"{prefix} PRS_info and full_prs IID sets differ")
        if int(record.get("duplicate_full_prs_iids") or 0) != 0 or int(record.get("duplicate_prs_iids") or 0) != 0:
            errors.append(f"{prefix} duplicate IIDs are present")
        try:
            z_error = float(record.get("z_formula_max_abs_error"))
        except (TypeError, ValueError):
            z_error = float("inf")
        if z_error > 1e-8:
            errors.append(f"{prefix} supplied z scores fail the documented formula check")
        try:
            pct_min = float(record.get("pct_min"))
            pct_max = float(record.get("pct_max"))
        except (TypeError, ValueError):
            pct_min, pct_max = -1.0, 2.0
        if pct_min < 0.0 or pct_max > 100.0:
            errors.append(f"{prefix} percentile values fall outside [0, 100]")
        try:
            ref_sd = float(record.get("ref_sd"))
        except (TypeError, ValueError):
            ref_sd = 0.0
        if ref_sd <= 0:
            errors.append(f"{prefix} ref_sd must be positive")
        try:
            prs_rows = int(record.get("prs_rows"))
            annotated_rows = int(record.get("annotated_rows"))
            variance_non_missing = int(record.get("variance_non_missing"))
            rank_one_rows = int(record.get("rank_one_rows"))
        except (TypeError, ValueError):
            prs_rows = annotated_rows = variance_non_missing = rank_one_rows = -1
        if prs_rows != annotated_rows or variance_non_missing != annotated_rows:
            errors.append(f"{prefix} gene rows or variance metadata are incomplete")
        if rank_one_rows < 1:
            errors.append(f"{prefix} no within-region variance representatives were found")
    return records, errors


def run_r_audit(rds_dir: Path, rare_tsv: Path) -> pd.DataFrame:
    rscript = shutil.which("Rscript")
    if not rscript:
        raise RuntimeError("Rscript is not available on PATH")
    with tempfile.TemporaryDirectory(prefix="xprs_kfda_audit_") as temporary:
        temp_dir = Path(temporary)
        script_path = temp_dir / "audit.R"
        output_path = temp_dir / "rds_audit.tsv"
        script_path.write_text(R_AUDIT_SCRIPT, encoding="utf-8")
        completed = subprocess.run(
            [rscript, str(script_path), str(rds_dir), str(rare_tsv), str(output_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "RDS audit failed").strip()
            detail = detail.replace(str(rds_dir), "<private-rds-dir>")
            detail = detail.replace(str(rare_tsv), "<private-rare-tsv>")
            raise RuntimeError(detail)
        return pd.read_csv(output_path, sep="\t")


def _path_is_inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def write_private_manifest(path: Path, manifest: dict[str, Any]) -> None:
    if _path_is_inside_repo(path):
        raise ValueError("Audit output must be written outside the public repository")
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    rds_dir = args.rds_dir.expanduser().resolve()
    rare_tsv = args.rare_tsv.expanduser().resolve()
    if not rds_dir.is_dir():
        raise FileNotFoundError("RDS directory does not exist")
    if not rare_tsv.is_file():
        raise FileNotFoundError("Rare-variant TSV does not exist")

    rare_summary, rare_errors = summarize_rare_findings(rare_tsv)
    rds_frame = run_r_audit(rds_dir, rare_tsv)
    rds_records, rds_errors = validate_rds_audit(rds_frame)
    errors = [*rare_errors, *rds_errors]
    cohort_sample_counts = {
        int(record["prs_columns"])
        for record in rds_records
        if record.get("prs_columns") is not None
    }
    cohort_sample_count = next(iter(cohort_sample_counts)) if len(cohort_sample_counts) == 1 else None
    if cohort_sample_count is not None and rare_summary["finding_iids"] > cohort_sample_count:
        errors.append("Rare-variant finding IID count exceeds the RDS cohort size")

    if args.hash_files:
        print("Computing source checksums...", flush=True)
        rare_summary["sha256"] = sha256_file(rare_tsv)
        for record in rds_records:
            source_path = rds_dir / str(record["source_filename"])
            if source_path.is_file():
                record["sha256"] = sha256_file(source_path)
                record["bytes"] = source_path.stat().st_size

    return {
        "schema_version": 1,
        "handoff_id": str(args.handoff_id).strip() or "private-cohort-handoff",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contains_participant_ids": False,
        "source_paths_recorded": False,
        "percentile_scale": "percent_0_100",
        "cohort_sample_count": cohort_sample_count,
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "rare_variants": rare_summary,
        "diseases": sorted(rds_records, key=lambda item: str(item.get("source_stem") or "")),
    }


def main() -> int:
    args = parse_args()
    try:
        manifest = build_manifest(args)
        if args.output:
            write_private_manifest(args.output, manifest)
    except (FileNotFoundError, OSError, RuntimeError, ValueError, pd.errors.ParserError) as exc:
        print(f"Audit could not complete: {exc}", file=sys.stderr)
        return 2

    rare = manifest["rare_variants"]
    print(f"Handoff: {manifest['handoff_id']}")
    print(
        f"Rare variants: {rare['rows']} rows; {rare['alert_rows']} alerts; "
        f"{rare['carrier_rows']} carriers; {rare['alert_iids']} alert-positive individuals"
    )
    print(f"Disease RDS files audited: {len(manifest['diseases'])}")
    for disease in manifest["diseases"]:
        print(
            f"  {disease.get('source_stem')}: genes={disease.get('prs_rows')} "
            f"individuals={disease.get('prs_columns')} applicable={disease.get('pct_non_missing')}"
        )
    print(f"Result: {manifest['status'].upper()} ({len(manifest['errors'])} errors)")
    for error in manifest["errors"]:
        print(f"  ERROR: {error}")
    if args.output:
        print(f"Aggregate manifest written with mode 0600: {args.output.expanduser().resolve()}")
    return 0 if manifest["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
