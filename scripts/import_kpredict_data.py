#!/usr/bin/env python3
"""Import the private K-PREDICT handoff into a versioned, pseudonymous store."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_kfda_handoff import (
    EXPECTED_DISEASES,
    build_manifest as build_audit_manifest,
)
from kpredict_schema import normalize_kpredict_disease


COHORT_SLUG = "kpredict"
COHORT_LABEL = "K-PREDICT"


R_EXTRACT_IIDS = r'''
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) stop("Expected <rds_path> <output_tsv>", call. = FALSE)
d <- readRDS(args[[1]])
iids <- names(d$PRS_info)
if (is.null(iids) || any(iids == "") || anyDuplicated(iids)) {
  stop("PRS_info must have unique, non-empty IID column names", call. = FALSE)
}
write.table(
  data.frame(source_iid = iids, stringsAsFactors = FALSE),
  args[[2]], sep = "\t", row.names = FALSE, quote = TRUE, na = ""
)
'''


R_EXPORT_DISEASE = r'''
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 4) {
  stop("Expected <rds_path> <id_map_tsv> <output_dir> <binary_name>", call. = FALSE)
}
rds_path <- args[[1]]
id_map_path <- args[[2]]
output_dir <- args[[3]]
binary_name <- args[[4]]
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE, mode = "0700")

d <- readRDS(rds_path)
id_map <- read.delim(id_map_path, sep = "\t", header = TRUE, stringsAsFactors = FALSE, check.names = FALSE)
prs_iids <- names(d$PRS_info)
full_iids <- as.character(d$full_prs$IID)
map_index <- match(prs_iids, id_map$source_iid)
full_index <- match(prs_iids, full_iids)
if (anyNA(map_index) || anyNA(full_index)) stop("IID mapping is incomplete", call. = FALSE)

z_values <- as.numeric(d$z)[full_index]
pct_values <- as.numeric(d$pct)[full_index]

sex_values <- rep(NA_character_, length(prs_iids))
if (!is.null(d$fam) && !is.null(dim(d$fam)) && ncol(d$fam) >= 5) {
  fam <- as.data.frame(d$fam, stringsAsFactors = FALSE)
  overlaps <- vapply(fam, function(column) sum(full_iids %in% as.character(column)), numeric(1))
  iid_column <- names(which.max(overlaps))
  fam_index <- match(prs_iids, as.character(fam[[iid_column]]))
  sex_code <- as.character(fam[[5]][fam_index])
  sex_values[sex_code == "1"] <- "M"
  sex_values[sex_code == "2"] <- "F"
  sex_values[is.na(sex_values)] <- "U"
}

risk <- data.frame(
  individual_id = id_map$pseudonym[map_index],
  matrix_column = seq_along(prs_iids) - 1L,
  sex = sex_values,
  raw_prs = as.numeric(d$full_prs$PRS)[full_index],
  z = z_values,
  percentile = pct_values,
  applicable = is.finite(z_values) & is.finite(pct_values),
  stringsAsFactors = FALSE
)
write.table(
  risk, file.path(output_dir, "individual_risk.tsv"),
  sep = "\t", row.names = FALSE, quote = TRUE, na = ""
)

gene_columns <- intersect(
  c("chr", "symbol", "start", "end", "snps_count", "region", "mean", "variance", "within_region_rank_by_variance"),
  names(d$annotated_info)
)
genes <- as.data.frame(d$annotated_info, stringsAsFactors = FALSE)[, gene_columns, drop = FALSE]
genes <- cbind(data.frame(matrix_row = seq_len(nrow(genes)) - 1L), genes)
write.table(
  genes, file.path(output_dir, "genes.tsv"),
  sep = "\t", row.names = FALSE, quote = TRUE, na = ""
)

metadata <- data.frame(
  disease_id = as.character(d$disease_id[[1]]),
  disease_label = if (!is.null(d$disease_label)) as.character(d$disease_label[[1]]) else "",
  gene_count = nrow(d$PRS_info),
  individual_count = ncol(d$PRS_info),
  ref_mean = as.numeric(d$ref_mean[[1]]),
  ref_sd = as.numeric(d$ref_sd[[1]]),
  reference_cohort = if (!is.null(d$reference_cohort)) as.character(d$reference_cohort[[1]]) else "",
  stringsAsFactors = FALSE
)
write.table(
  metadata, file.path(output_dir, "metadata.tsv"),
  sep = "\t", row.names = FALSE, quote = TRUE, na = ""
)

binary_path <- file.path(output_dir, binary_name)
connection <- file(binary_path, open = "wb")
for (iid in prs_iids) {
  values <- as.numeric(d$PRS_info[[iid]])
  if (length(values) != nrow(d$PRS_info)) stop("Contribution column length mismatch", call. = FALSE)
  writeBin(values, connection, size = 4L, endian = "little")
}
close(connection)

probe_columns <- unique(as.integer(round(seq(1, ncol(d$PRS_info), length.out = 25))))
connection <- file(binary_path, open = "rb")
max_abs_error <- 0
squared_error <- 0
compared_values <- 0
top10_mismatches <- 0L
bottom10_mismatches <- 0L
for (column_index in probe_columns) {
  seek(connection, where = (column_index - 1) * nrow(d$PRS_info) * 4, origin = "start")
  observed <- readBin(connection, what = double(), n = nrow(d$PRS_info), size = 4L, endian = "little")
  expected <- as.numeric(d$PRS_info[[column_index]])
  keep <- is.finite(observed) & is.finite(expected)
  delta <- abs(observed[keep] - expected[keep])
  if (length(delta)) {
    max_abs_error <- max(max_abs_error, delta)
    squared_error <- squared_error + sum(delta ^ 2)
    compared_values <- compared_values + length(delta)
  }
  top10_mismatches <- top10_mismatches + as.integer(
    !identical(order(observed, decreasing = TRUE)[1:10], order(expected, decreasing = TRUE)[1:10])
  )
  bottom10_mismatches <- bottom10_mismatches + as.integer(
    !identical(order(observed, decreasing = FALSE)[1:10], order(expected, decreasing = FALSE)[1:10])
  )
}
close(connection)
precision <- data.frame(
  probe_columns = length(probe_columns),
  compared_values = compared_values,
  max_abs_error = max_abs_error,
  rmse = if (compared_values) sqrt(squared_error / compared_values) else NA_real_,
  top10_mismatches = top10_mismatches,
  bottom10_mismatches = bottom10_mismatches
)
write.table(
  precision, file.path(output_dir, "precision_validation.tsv"),
  sep = "\t", row.names = FALSE, quote = TRUE, na = ""
)
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rds-dir", type=Path, required=True)
    parser.add_argument("--rare-tsv", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--release", required=True, help="Version directory, for example 2026-09-17")
    parser.add_argument("--handoff-id", default="private-cohort-handoff")
    parser.add_argument(
        "--audit-manifest",
        type=Path,
        help="Previously generated passing aggregate audit manifest; avoids re-reading every RDS.",
    )
    parser.add_argument(
        "--skip-source-hashes",
        action="store_true",
        help="Skip source SHA-256 checksums (not recommended for a frozen release).",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def path_is_inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def validate_release_name(value: str) -> str:
    value = value.strip()
    if not value or value in {".", ".."} or any(character not in "0123456789-.v_" for character in value):
        raise ValueError("Release must contain only numbers, letters v, dots, hyphens, or underscores")
    return value


def write_json_private(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def run_r_script(script: str, arguments: list[Path | str], temporary_dir: Path) -> None:
    rscript = shutil.which("Rscript")
    if not rscript:
        raise RuntimeError("Rscript is not available on PATH")
    script_path = temporary_dir / f"import_{uuid.uuid4().hex}.R"
    script_path.write_text(script, encoding="utf-8")
    script_path.chmod(0o600)
    completed = subprocess.run(
        [rscript, str(script_path), *[str(argument) for argument in arguments]],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "R export failed").strip()
        raise RuntimeError(detail)


def make_pseudonym(source_iid: str, key: bytes) -> str:
    digest = hmac.new(key, source_iid.encode("utf-8"), hashlib.sha256).hexdigest()[:12].upper()
    return f"KP-{digest}"


def build_id_map(source_iids: list[str], key: bytes) -> pd.DataFrame:
    if not source_iids or len(source_iids) != len(set(source_iids)):
        raise ValueError("Source IID list must be non-empty and unique")
    mapping = pd.DataFrame({
        "source_iid": source_iids,
        "pseudonym": [make_pseudonym(iid, key) for iid in source_iids],
    })
    if mapping["pseudonym"].duplicated().any():
        raise ValueError("Pseudonym collision detected")
    return mapping


def load_or_run_audit(args: argparse.Namespace) -> dict[str, Any]:
    if args.audit_manifest:
        audit_path = args.audit_manifest.expanduser().resolve()
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    else:
        audit_args = argparse.Namespace(
            rds_dir=args.rds_dir,
            rare_tsv=args.rare_tsv,
            output=None,
            hash_files=False,
            handoff_id=args.handoff_id,
        )
        audit = build_audit_manifest(audit_args)
    if audit.get("status") != "pass":
        raise ValueError("The source handoff has not passed the structural audit")
    if audit.get("contains_participant_ids") is not False or audit.get("source_paths_recorded") is not False:
        raise ValueError("Audit manifest does not satisfy the aggregate-only contract")
    disease_ids = {str(item.get("source_stem")) for item in audit.get("diseases", [])}
    if disease_ids != set(EXPECTED_DISEASES):
        raise ValueError("Audit manifest disease set does not match the importer contract")
    return audit


def normalize_gene_table(frame: pd.DataFrame) -> pd.DataFrame:
    integer_columns = ("matrix_row", "start", "end", "snps_count", "within_region_rank_by_variance")
    float_columns = ("mean", "variance")
    for column in integer_columns:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Int64")
    for column in float_columns:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def normalize_risk_table(frame: pd.DataFrame) -> pd.DataFrame:
    frame["matrix_column"] = pd.to_numeric(frame["matrix_column"], errors="raise").astype("int32")
    for column in ("raw_prs", "z", "percentile"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["applicable"] = frame["applicable"].astype(str).str.upper().eq("TRUE")
    return frame


def import_disease(
    *,
    source_path: Path,
    disease_id: str,
    portal_slug: str,
    id_map_tsv: Path,
    output_dir: Path,
    temporary_dir: Path,
    hash_sources: bool,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, mode=0o700)
    binary_name = "contributions.f32"
    run_r_script(
        R_EXPORT_DISEASE,
        [source_path, id_map_tsv, output_dir, binary_name],
        temporary_dir,
    )

    risk_tsv = output_dir / "individual_risk.tsv"
    genes_tsv = output_dir / "genes.tsv"
    metadata_tsv = output_dir / "metadata.tsv"
    precision_tsv = output_dir / "precision_validation.tsv"
    risk = normalize_risk_table(pd.read_csv(risk_tsv, sep="\t", dtype={"individual_id": str, "sex": str}))
    genes = normalize_gene_table(pd.read_csv(genes_tsv, sep="\t", dtype={"chr": str, "symbol": str, "region": str}))
    metadata = pd.read_csv(metadata_tsv, sep="\t").iloc[0].to_dict()
    precision = pd.read_csv(precision_tsv, sep="\t").iloc[0].to_dict()

    if str(metadata.get("disease_id")) != disease_id:
        raise ValueError(f"{disease_id}: exported disease_id does not match filename")
    gene_count = int(metadata["gene_count"])
    individual_count = int(metadata["individual_count"])
    if len(genes) != gene_count or len(risk) != individual_count:
        raise ValueError(f"{disease_id}: exported table dimensions do not match RDS metadata")
    if risk["individual_id"].duplicated().any():
        raise ValueError(f"{disease_id}: duplicate pseudonymous individual IDs")

    binary_path = output_dir / binary_name
    expected_bytes = gene_count * individual_count * np.dtype("<f4").itemsize
    if binary_path.stat().st_size != expected_bytes:
        raise ValueError(
            f"{disease_id}: contribution matrix expected {expected_bytes} bytes, "
            f"found {binary_path.stat().st_size}"
        )
    if (
        float(precision["max_abs_error"]) > 1e-6
        or int(precision["top10_mismatches"]) != 0
        or int(precision["bottom10_mismatches"]) != 0
    ):
        raise ValueError(f"{disease_id}: float32 precision validation failed")

    risk_path = output_dir / "individual_risk.parquet"
    genes_path = output_dir / "genes.parquet"
    risk.to_parquet(risk_path, index=False, compression="zstd")
    genes.to_parquet(genes_path, index=False, compression="zstd")

    for temporary_path in (risk_tsv, genes_tsv, metadata_tsv, precision_tsv):
        temporary_path.unlink()
    for path in (binary_path, risk_path, genes_path):
        path.chmod(0o600)

    matrix_metadata = {
        "schema_version": 1,
        "dtype": "float32",
        "byte_order": "little",
        "layout": "column_major",
        "shape": [gene_count, individual_count],
        "row_index": "genes.parquet:matrix_row",
        "column_index": "individual_risk.parquet:matrix_column",
        "data_file": binary_name,
    }
    matrix_metadata_path = output_dir / "matrix.json"
    write_json_private(matrix_metadata_path, matrix_metadata)

    files = {}
    for path in (binary_path, risk_path, genes_path, matrix_metadata_path):
        files[path.name] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    source = {"filename": source_path.name, "bytes": source_path.stat().st_size}
    if hash_sources:
        source["sha256"] = sha256_file(source_path)
    return {
        "source_disease_id": disease_id,
        "portal_disease_slug": portal_slug,
        "disease_label": str(metadata.get("disease_label") or ""),
        "gene_count": gene_count,
        "representative_gene_rows": int(
            pd.to_numeric(genes.get("within_region_rank_by_variance"), errors="coerce").eq(1).sum()
        ),
        "individual_count": individual_count,
        "applicable_count": int(risk["applicable"].sum()),
        "ref_mean": float(metadata["ref_mean"]),
        "ref_sd": float(metadata["ref_sd"]),
        "percentile_scale": "percent_0_100",
        "float32_validation": {
            "probe_columns": int(precision["probe_columns"]),
            "compared_values": int(precision["compared_values"]),
            "max_abs_error": float(precision["max_abs_error"]),
            "rmse": float(precision["rmse"]),
            "top10_mismatches": int(precision["top10_mismatches"]),
            "bottom10_mismatches": int(precision["bottom10_mismatches"]),
        },
        "source": source,
        "files": files,
    }


def import_rare_findings(
    source_path: Path,
    mapping: pd.DataFrame,
    key: bytes,
    output_dir: Path,
    *,
    hash_source: bool,
) -> dict[str, Any]:
    data = pd.read_csv(source_path, sep="\t", dtype=str)
    pseudonym_by_source = mapping.set_index("source_iid")["pseudonym"]
    pseudonyms = data["IID"].map(pseudonym_by_source)
    if pseudonyms.isna().any():
        raise ValueError("Rare findings contain IIDs absent from the RDS cohort")
    data = data.drop(columns=["IID"])
    data.insert(0, "individual_id", pseudonyms)
    composite = (
        data["individual_id"].fillna("")
        + "|" + data["variant"].fillna("")
        + "|" + data["gene"].fillna("")
        + "|" + data["xprs_disease"].fillna("")
        + "|" + data["track"].fillna("")
    )
    data.insert(
        0,
        "finding_id",
        [
            "RF-" + hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:16].upper()
            for value in composite
        ],
    )
    if data["finding_id"].duplicated().any():
        raise ValueError("Rare-finding pseudonymous identifiers are not unique")

    # Preserve finding IDs derived from the supplied source key, then store the
    # portal-facing disease slug for consistent runtime matching. Existing
    # releases are normalized defensively by kpredict_data.rare_findings().
    panel_mask = data["track"].eq("panel")
    data.loc[panel_mask, "xprs_disease"] = data.loc[
        panel_mask, "xprs_disease"
    ].map(normalize_kpredict_disease)

    for column in ("panelapp_n_panels", "stars"):
        if column in data:
            data[column] = pd.to_numeric(data[column], errors="coerce").astype("Int64")
    for column in ("gnomad_af", "gnomad_af_eas", "cohort_af"):
        if column in data:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    if "qc_pass" in data:
        data["qc_pass"] = data["qc_pass"].astype(str).str.lower().eq("true")

    data = data.sort_values(
        ["individual_id", "track", "xprs_disease", "gene", "finding_id"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)
    findings_path = output_dir / "rare_findings.parquet"
    data.to_parquet(findings_path, index=False, compression="zstd")
    findings_path.chmod(0o600)

    index_source = data.assign(
        _alert=data["moi_call"].eq("alert").astype("int32"),
        _carrier=data["moi_call"].eq("carrier").astype("int32"),
        _panel_alert=(data["track"].eq("panel") & data["moi_call"].eq("alert")).astype("int32"),
        _other_alert=(data["track"].eq("other") & data["moi_call"].eq("alert")).astype("int32"),
    )
    index = (
        index_source.groupby("individual_id", sort=True)
        .agg(
            finding_count=("finding_id", "size"),
            alert_count=("_alert", "sum"),
            carrier_count=("_carrier", "sum"),
            panel_alert_count=("_panel_alert", "sum"),
            other_alert_count=("_other_alert", "sum"),
        )
        .reset_index()
    )
    index_path = output_dir / "rare_finding_index.parquet"
    index.to_parquet(index_path, index=False, compression="zstd")
    index_path.chmod(0o600)

    source = {"filename": source_path.name, "bytes": source_path.stat().st_size}
    if hash_source:
        source["sha256"] = sha256_file(source_path)
    return {
        "source": source,
        "finding_count": int(len(data)),
        "individuals_with_findings": int(data["individual_id"].nunique()),
        "alert_count": int(data["moi_call"].eq("alert").sum()),
        "carrier_count": int(data["moi_call"].eq("carrier").sum()),
        "files": {
            findings_path.name: {"bytes": findings_path.stat().st_size, "sha256": sha256_file(findings_path)},
            index_path.name: {"bytes": index_path.stat().st_size, "sha256": sha256_file(index_path)},
        },
    }


def secure_tree(root: Path) -> None:
    for directory, subdirectories, filenames in os.walk(root):
        Path(directory).chmod(0o700)
        for name in subdirectories:
            (Path(directory) / name).chmod(0o700)
        for name in filenames:
            (Path(directory) / name).chmod(0o600)


def run_import(args: argparse.Namespace) -> Path:
    rds_dir = args.rds_dir.expanduser().resolve()
    rare_tsv = args.rare_tsv.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    release = validate_release_name(args.release)
    if path_is_inside_repo(output_root):
        raise ValueError("Private import output must be outside the public repository")
    if not rds_dir.is_dir() or not rare_tsv.is_file():
        raise FileNotFoundError("Private source directory or rare-finding TSV is missing")

    audit = load_or_run_audit(args)
    cohort_root = output_root / COHORT_SLUG
    target = cohort_root / release
    if target.exists():
        raise FileExistsError(f"Release already exists: {target}")
    output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_root.chmod(0o700)
    cohort_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    cohort_root.chmod(0o700)
    staging = cohort_root / f".{release}.staging-{uuid.uuid4().hex}"
    staging.mkdir(mode=0o700)

    with tempfile.TemporaryDirectory(prefix="xprs_kpredict_import_") as temporary:
        temporary_dir = Path(temporary)
        temporary_dir.chmod(0o700)
        try:
            first_disease = sorted(EXPECTED_DISEASES)[0]
            first_rds = rds_dir / f"{first_disease}_cohort.RDS"
            source_iids_path = temporary_dir / "source_iids.tsv"
            run_r_script(R_EXTRACT_IIDS, [first_rds, source_iids_path], temporary_dir)
            source_iids = pd.read_csv(source_iids_path, sep="\t", dtype=str)["source_iid"].tolist()

            pseudonym_key = secrets.token_bytes(32)
            mapping = build_id_map(source_iids, pseudonym_key)
            restricted = staging / "_restricted"
            restricted.mkdir(mode=0o700)
            key_path = restricted / "pseudonym_hmac.key"
            key_path.write_bytes(pseudonym_key)
            key_path.chmod(0o600)
            mapping_path = restricted / "id_map.parquet"
            mapping.to_parquet(mapping_path, index=False, compression="zstd")
            mapping_path.chmod(0o600)
            id_map_tsv = temporary_dir / "id_map.tsv"
            mapping.to_csv(id_map_tsv, sep="\t", index=False)
            id_map_tsv.chmod(0o600)

            disease_manifests = []
            for number, disease_id in enumerate(sorted(EXPECTED_DISEASES), start=1):
                print(f"[{number}/{len(EXPECTED_DISEASES)}] Importing {disease_id}...", flush=True)
                source_path = rds_dir / f"{disease_id}_cohort.RDS"
                if not source_path.is_file():
                    raise FileNotFoundError(f"Missing expected RDS file: {source_path.name}")
                disease_manifests.append(import_disease(
                    source_path=source_path,
                    disease_id=disease_id,
                    portal_slug=EXPECTED_DISEASES[disease_id]["portal_slug"],
                    id_map_tsv=id_map_tsv,
                    output_dir=staging / "diseases" / EXPECTED_DISEASES[disease_id]["portal_slug"],
                    temporary_dir=temporary_dir,
                    hash_sources=not args.skip_source_hashes,
                ))

            print("Importing rare findings...", flush=True)
            rare_manifest = import_rare_findings(
                rare_tsv,
                mapping,
                pseudonym_key,
                staging,
                hash_source=not args.skip_source_hashes,
            )

            manifest = {
                "schema_version": 1,
                "cohort_slug": COHORT_SLUG,
                "cohort_label": COHORT_LABEL,
                "release": release,
                "handoff_id": str(args.handoff_id),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "private_data": True,
                "browser_ids_pseudonymous": True,
                "source_paths_recorded": False,
                "individual_count": int(len(mapping)),
                "percentile_scale": "percent_0_100",
                "contribution_dtype": "float32",
                "audit": {
                    "status": audit.get("status"),
                    "generated_at": audit.get("generated_at"),
                    "schema_version": audit.get("schema_version"),
                },
                "diseases": disease_manifests,
                "rare_findings": rare_manifest,
                "restricted_files": [
                    "_restricted/id_map.parquet",
                    "_restricted/pseudonym_hmac.key",
                ],
            }
            write_json_private(staging / "manifest.json", manifest)
            secure_tree(staging)
            staging.replace(target)
            secure_tree(target)
            return target
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise


def main() -> int:
    os.umask(0o077)
    args = parse_args()
    try:
        target = run_import(args)
    except (FileNotFoundError, FileExistsError, OSError, RuntimeError, ValueError, pd.errors.ParserError) as exc:
        detail = str(exc)
        detail = detail.replace(str(args.rds_dir.expanduser().resolve()), "<private-rds-dir>")
        detail = detail.replace(str(args.rare_tsv.expanduser().resolve()), "<private-rare-tsv>")
        print(f"Import failed: {detail}", file=sys.stderr)
        return 1
    print(f"K-PREDICT import complete: {target}")
    print("The derived release uses pseudonymous IDs and mode-0600 files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
