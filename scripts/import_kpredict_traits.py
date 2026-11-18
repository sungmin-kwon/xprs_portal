#!/usr/bin/env python3
"""Add K-PREDICT continuous-trait PRS to a new release built on an existing one.

The 42 continuous traits (LDL, glucose, eGFR, ...) are not part of the disease
handoff; DATA_GUIDE.md points to a separate folder with a different structure:

- ``<TRAIT>_cohort.RDS``: ``gene_matrix`` is people x genes (the transpose of
  the disease ``PRS_info``), ``prs_all``/``z``/``pct`` are plain vectors in
  ``fam`` order, and IIDs are in ``fam`` column 2 (PLINK convention).
- ``cohort_prs.tsv``: PRS, z and percentile for all traits (cross-checked here).
- ``cohort_sex.tsv``, ``cohort_summary.tsv``: sex and per-trait metadata.

The new release hard-links every file of the base release except
``manifest.json`` (diseases, rare findings, restricted ID map), so the disease
data costs no extra space, and adds ``traits/<slug>/`` with the same file
layout as ``diseases/<slug>/``. Releases are write-once: never edit a release
in place, because hard-linked files are shared with the base release.

Pseudonyms come from the base release's ID map. The import stops unless every
trait file has exactly the base release's individuals.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
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

from scripts.import_kpredict_data import (  # noqa: E402
    normalize_gene_table,
    normalize_risk_table,
    path_is_inside_repo,
    run_r_script,
    secure_tree,
    sha256_file,
    validate_release_name,
    write_json_private,
)


# Values from the RDS must agree with cohort_prs.tsv; both come from the same
# pipeline run, so anything beyond floating-point noise means a mismatch.
CROSS_CHECK_TOLERANCE = 1e-6
MATRIX_FILE = "contributions.f32"


R_EXPORT_TRAIT = r'''
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
g <- d$gene_matrix
fam <- as.data.frame(d$fam, stringsAsFactors = FALSE)
iids <- as.character(fam[[2]])
if (!identical(as.character(rownames(g)), iids)) stop("gene_matrix rows are not in fam order", call. = FALSE)
if (length(d$prs_all) != nrow(g) || length(d$z) != nrow(g) || length(d$pct) != nrow(g)) {
  stop("prs_all/z/pct length does not match gene_matrix", call. = FALSE)
}
map_index <- match(iids, id_map$source_iid)
if (anyNA(map_index)) stop("IID mapping is incomplete", call. = FALSE)

annotated <- as.data.frame(d$annotated_info, stringsAsFactors = FALSE)
if (!identical(as.character(annotated$symbol), colnames(g))) {
  stop("annotated_info symbols are not in gene_matrix column order", call. = FALSE)
}

sex_code <- as.character(fam[[5]])
sex_values <- rep("U", length(iids))
sex_values[sex_code == "1"] <- "M"
sex_values[sex_code == "2"] <- "F"

z_values <- as.numeric(d$z)
pct_values <- as.numeric(d$pct)
risk <- data.frame(
  individual_id = id_map$pseudonym[map_index],
  matrix_column = seq_along(iids) - 1L,
  sex = sex_values,
  raw_prs = as.numeric(d$prs_all),
  z = z_values,
  percentile = pct_values,
  applicable = is.finite(z_values) & is.finite(pct_values),
  stringsAsFactors = FALSE
)
write.table(risk, file.path(output_dir, "individual_risk.tsv"), sep = "\t", row.names = FALSE, quote = TRUE, na = "")

if ("snps_sharing_genes" %in% names(annotated) && is.list(annotated$snps_sharing_genes)) {
  annotated$snps_sharing_genes <- vapply(
    annotated$snps_sharing_genes,
    function(value) paste(as.character(unlist(value)), collapse = ";"),
    character(1)
  )
}
gene_columns <- intersect(
  c("chr", "symbol", "start", "end", "snps_count", "region", "mean", "variance",
    "within_region_rank_by_variance", "snps_sharing_genes"),
  names(annotated)
)
genes <- annotated[, gene_columns, drop = FALSE]
genes <- cbind(data.frame(matrix_row = seq_len(nrow(genes)) - 1L), genes)
write.table(genes, file.path(output_dir, "genes.tsv"), sep = "\t", row.names = FALSE, quote = TRUE, na = "")

metadata <- data.frame(
  trait_id = as.character(d$disease_id[[1]]),
  trait_label = if (!is.null(d$disease_label)) as.character(d$disease_label[[1]]) else "",
  gene_count = ncol(g),
  individual_count = nrow(g),
  ref_mean = as.numeric(d$ref_mean[[1]]),
  ref_sd = as.numeric(d$ref_sd[[1]]),
  reference_cohort = if (!is.null(d$reference_cohort)) as.character(d$reference_cohort[[1]]) else "",
  built = if (!is.null(d$built)) as.character(d$built[[1]]) else "",
  stringsAsFactors = FALSE
)
write.table(metadata, file.path(output_dir, "metadata.tsv"), sep = "\t", row.names = FALSE, quote = TRUE, na = "")

# Store genes x people in column-major order (one contiguous column per
# person), the same layout as the disease matrices. Row i of the people x genes
# matrix is person i's column, so write rows in chunks.
binary_path <- file.path(output_dir, binary_name)
connection <- file(binary_path, open = "wb")
chunk <- 256L
for (start in seq(1L, nrow(g), by = chunk)) {
  rows <- start:min(start + chunk - 1L, nrow(g))
  writeBin(as.vector(t(g[rows, , drop = FALSE])), connection, size = 4L, endian = "little")
}
close(connection)

probe_columns <- unique(as.integer(round(seq(1, nrow(g), length.out = 25))))
connection <- file(binary_path, open = "rb")
max_abs_error <- 0
squared_error <- 0
compared_values <- 0
top10_mismatches <- 0L
bottom10_mismatches <- 0L
for (person in probe_columns) {
  seek(connection, where = (person - 1) * ncol(g) * 4, origin = "start")
  observed <- readBin(connection, what = double(), n = ncol(g), size = 4L, endian = "little")
  expected <- as.numeric(g[person, ])
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
write.table(precision, file.path(output_dir, "precision_validation.tsv"), sep = "\t", row.names = FALSE, quote = TRUE, na = "")
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-release", type=Path, required=True,
                        help="Existing release directory, e.g. .../kpredict/2026-11-18")
    parser.add_argument("--continuous-dir", type=Path, required=True,
                        help="Folder with <TRAIT>_cohort.RDS, cohort_prs.tsv, cohort_sex.tsv, cohort_summary.tsv")
    parser.add_argument("--release", required=True, help="New release directory name, e.g. 2026-11-19")
    parser.add_argument("--only", nargs="*", default=None,
                        help="Import only these trait IDs (for a quick trial into a throwaway release)")
    parser.add_argument("--skip-source-hashes", action="store_true",
                        help="Skip SHA-256 of the source RDS files (not recommended for a frozen release).")
    return parser.parse_args()


def trait_slug(trait_id: str) -> str:
    """Portal slug for a trait ID: lower case, letters/digits/underscores only."""
    slug = "".join(character if character.isalnum() else "_" for character in trait_id.strip().lower())
    if not slug or not slug[0].isalpha():
        raise ValueError(f"Cannot build a portal slug from trait ID {trait_id!r}")
    return slug


def link_base_release(base: Path, staging: Path) -> int:
    """Hard-link every file of the base release into staging, except manifest.json.

    Returns the number of linked files. Hard links need both directories on the
    same filesystem, which holds for sibling release directories.
    """
    linked = 0
    for directory, _subdirectories, filenames in os.walk(base):
        relative = Path(directory).relative_to(base)
        (staging / relative).mkdir(parents=True, exist_ok=True, mode=0o700)
        for name in filenames:
            if relative == Path(".") and name == "manifest.json":
                continue
            os.link(Path(directory) / name, staging / relative / name)
            linked += 1
    return linked


def cross_check_risk(
    trait_id: str,
    risk: pd.DataFrame,
    prs_table: pd.DataFrame,
    sex_table: pd.DataFrame,
    pseudonym_by_iid: pd.Series,
) -> dict[str, float]:
    """Compare the RDS export with cohort_prs.tsv and cohort_sex.tsv.

    ``risk`` has pseudonymous ``individual_id``; the tables are keyed by source
    ``IID`` and are translated with ``pseudonym_by_iid`` (index: IID).
    Raises ValueError on any membership or value mismatch.
    """
    columns = {"raw_prs": f"{trait_id}_PRS", "z": f"{trait_id}_z", "percentile": f"{trait_id}_pct"}
    missing = [column for column in columns.values() if column not in prs_table]
    if missing:
        raise ValueError(f"{trait_id}: cohort_prs.tsv lacks {missing}")
    table = prs_table.assign(individual_id=prs_table["IID"].astype(str).map(pseudonym_by_iid))
    if table["individual_id"].isna().any():
        raise ValueError(f"{trait_id}: cohort_prs.tsv has individuals outside the base release")
    merged = risk.merge(table, on="individual_id", how="outer", indicator=True, validate="one_to_one")
    if not merged["_merge"].eq("both").all():
        raise ValueError(f"{trait_id}: individuals differ between the RDS and cohort_prs.tsv")
    differences = {}
    for risk_column, table_column in columns.items():
        difference = float(np.nanmax(np.abs(merged[risk_column].to_numpy(float) - merged[table_column].to_numpy(float))))
        if not difference <= CROSS_CHECK_TOLERANCE:
            raise ValueError(f"{trait_id}: {risk_column} differs from cohort_prs.tsv by {difference:.3g}")
        differences[risk_column] = difference

    sex = sex_table.assign(individual_id=sex_table["IID"].astype(str).map(pseudonym_by_iid))
    sex_code = sex.set_index("individual_id")["SEX"].astype(str).map({"1": "M", "2": "F"}).fillna("U")
    if not risk.set_index("individual_id")["sex"].eq(sex_code.reindex(risk["individual_id"])).all():
        raise ValueError(f"{trait_id}: sex differs from cohort_sex.tsv")
    return differences


def import_trait(
    *,
    source_path: Path,
    trait_id: str,
    summary: dict[str, Any],
    id_map_tsv: Path,
    output_dir: Path,
    temporary_dir: Path,
    prs_table: pd.DataFrame,
    sex_table: pd.DataFrame,
    pseudonym_by_iid: pd.Series,
    hash_source: bool,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, mode=0o700)
    run_r_script(R_EXPORT_TRAIT, [source_path, id_map_tsv, output_dir, MATRIX_FILE], temporary_dir)

    risk_tsv = output_dir / "individual_risk.tsv"
    genes_tsv = output_dir / "genes.tsv"
    metadata_tsv = output_dir / "metadata.tsv"
    precision_tsv = output_dir / "precision_validation.tsv"
    risk = normalize_risk_table(pd.read_csv(risk_tsv, sep="\t", dtype={"individual_id": str, "sex": str}))
    genes = normalize_gene_table(pd.read_csv(
        genes_tsv, sep="\t", dtype={"chr": str, "symbol": str, "region": str, "snps_sharing_genes": str}
    ))
    metadata = pd.read_csv(metadata_tsv, sep="\t", dtype={"trait_id": str}).iloc[0].to_dict()
    precision = pd.read_csv(precision_tsv, sep="\t").iloc[0].to_dict()

    if str(metadata["trait_id"]) != trait_id:
        raise ValueError(f"{trait_id}: exported trait ID does not match the filename")
    gene_count = int(metadata["gene_count"])
    individual_count = int(metadata["individual_count"])
    if len(genes) != gene_count or len(risk) != individual_count:
        raise ValueError(f"{trait_id}: exported table dimensions do not match the RDS")
    if individual_count != len(pseudonym_by_iid) or risk["individual_id"].duplicated().any():
        raise ValueError(f"{trait_id}: individuals do not match the base release")
    binary_path = output_dir / MATRIX_FILE
    expected_bytes = gene_count * individual_count * np.dtype("<f4").itemsize
    if binary_path.stat().st_size != expected_bytes:
        raise ValueError(f"{trait_id}: matrix expected {expected_bytes} bytes, found {binary_path.stat().st_size}")
    if (
        float(precision["max_abs_error"]) > 1e-6
        or int(precision["top10_mismatches"]) != 0
        or int(precision["bottom10_mismatches"]) != 0
    ):
        raise ValueError(f"{trait_id}: float32 precision validation failed")
    cross_check = cross_check_risk(trait_id, risk, prs_table, sex_table, pseudonym_by_iid)

    risk_path = output_dir / "individual_risk.parquet"
    genes_path = output_dir / "genes.parquet"
    risk.to_parquet(risk_path, index=False, compression="zstd")
    genes.to_parquet(genes_path, index=False, compression="zstd")
    for temporary_path in (risk_tsv, genes_tsv, metadata_tsv, precision_tsv):
        temporary_path.unlink()

    matrix_path = output_dir / "matrix.json"
    write_json_private(matrix_path, {
        "schema_version": 1,
        "dtype": "float32",
        "byte_order": "little",
        "layout": "column_major",
        "shape": [gene_count, individual_count],
        "row_index": "genes.parquet:matrix_row",
        "column_index": "individual_risk.parquet:matrix_column",
        "data_file": MATRIX_FILE,
    })
    files = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in (binary_path, risk_path, genes_path, matrix_path)
    }
    source = {"filename": source_path.name, "bytes": source_path.stat().st_size}
    if hash_source:
        source["sha256"] = sha256_file(source_path)
    return {
        "source_trait_id": trait_id,
        "portal_trait_slug": trait_slug(trait_id),
        "trait_label": str(metadata.get("trait_label") or summary.get("label") or trait_id),
        "gene_count": gene_count,
        "representative_gene_rows": int(
            pd.to_numeric(genes.get("within_region_rank_by_variance"), errors="coerce").eq(1).sum()
        ),
        "duplicate_gene_symbols": int(genes["symbol"].duplicated().sum()),
        "individual_count": individual_count,
        "applicable_count": int(risk["applicable"].sum()),
        "n_eligible": int(summary["n_eligible"]),
        "sex_restriction": str(summary["sex_restriction"]),
        "n_snps_scored": int(summary["n_snps_scored"]),
        "n_snps_used": int(summary["n_snps_used"]),
        "ref_mean": float(metadata["ref_mean"]),
        "ref_sd": float(metadata["ref_sd"]),
        "reference_cohort": str(metadata.get("reference_cohort") or ""),
        "source_built": str(metadata.get("built") or ""),
        "percentile_scale": "percent_0_100",
        "cross_check_max_abs_difference": cross_check,
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


def run_import(args: argparse.Namespace) -> Path:
    base = args.base_release.expanduser().resolve()
    continuous_dir = args.continuous_dir.expanduser().resolve()
    release = validate_release_name(args.release)
    cohort_root = base.parent
    if path_is_inside_repo(cohort_root):
        raise ValueError("Private release output must be outside the public repository")
    base_manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    if base_manifest.get("traits"):
        raise ValueError("Base release already contains traits; build on a disease-only release")
    target = cohort_root / release
    if target.exists():
        raise FileExistsError(f"Release already exists: {target.name}")

    id_map = pd.read_parquet(base / "_restricted" / "id_map.parquet")
    pseudonym_by_iid = id_map.set_index(id_map["source_iid"].astype(str))["pseudonym"]
    summary = pd.read_csv(continuous_dir / "cohort_summary.tsv", sep="\t", dtype={"id": str})
    prs_table = pd.read_csv(continuous_dir / "cohort_prs.tsv", sep="\t", dtype={"IID": str})
    sex_table = pd.read_csv(continuous_dir / "cohort_sex.tsv", sep="\t", dtype={"IID": str, "SEX": str})
    for name, table in (("cohort_prs.tsv", prs_table), ("cohort_sex.tsv", sex_table)):
        if set(table["IID"]) != set(pseudonym_by_iid.index) or table["IID"].duplicated().any():
            raise ValueError(f"{name}: individuals do not match the base release")
    trait_ids = summary["id"].tolist()
    if args.only:
        unknown = sorted(set(args.only) - set(trait_ids))
        if unknown:
            raise ValueError(f"Unknown trait IDs: {unknown}")
        trait_ids = [trait_id for trait_id in trait_ids if trait_id in set(args.only)]
    slugs = [trait_slug(trait_id) for trait_id in trait_ids]
    if len(set(slugs)) != len(slugs):
        raise ValueError("Two trait IDs map to the same portal slug")

    staging = cohort_root / f".{release}.staging-{uuid.uuid4().hex}"
    staging.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(prefix="xprs_kpredict_traits_") as temporary:
        temporary_dir = Path(temporary)
        try:
            linked = link_base_release(base, staging)
            print(f"Linked {linked} files from base release {base.name}.", flush=True)
            id_map_tsv = temporary_dir / "id_map.tsv"
            id_map.to_csv(id_map_tsv, sep="\t", index=False)
            id_map_tsv.chmod(0o600)

            trait_manifests = []
            summary_by_id = summary.set_index("id").to_dict(orient="index")
            for number, trait_id in enumerate(trait_ids, start=1):
                print(f"[{number}/{len(trait_ids)}] Importing {trait_id}...", flush=True)
                source_path = continuous_dir / f"{trait_id}_cohort.RDS"
                if not source_path.is_file():
                    raise FileNotFoundError(f"Missing trait file: {source_path.name}")
                trait_manifests.append(import_trait(
                    source_path=source_path,
                    trait_id=trait_id,
                    summary=summary_by_id[trait_id],
                    id_map_tsv=id_map_tsv,
                    output_dir=staging / "traits" / trait_slug(trait_id),
                    temporary_dir=temporary_dir,
                    prs_table=prs_table,
                    sex_table=sex_table,
                    pseudonym_by_iid=pseudonym_by_iid,
                    hash_source=not args.skip_source_hashes,
                ))

            manifest = dict(base_manifest)
            manifest.update({
                "release": release,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "derived_from_release": base.name,
                "pseudonyms_reused_from": base.name,
                "traits": trait_manifests,
                "traits_source": {
                    "description": "K-PREDICT continuous-trait PRS (separate folder named in DATA_GUIDE.md)",
                    "tables": {
                        name: {"bytes": (continuous_dir / name).stat().st_size,
                               "sha256": sha256_file(continuous_dir / name)}
                        for name in ("cohort_prs.tsv", "cohort_sex.tsv", "cohort_summary.tsv")
                    },
                },
            })
            write_json_private(staging / "manifest.json", manifest)
            secure_tree(staging)
            staging.replace(target)
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
        detail = str(exc).replace(str(args.continuous_dir.expanduser().resolve()), "<private-continuous-dir>")
        print(f"Trait import failed: {detail}", file=sys.stderr)
        return 1
    print(f"K-PREDICT trait release complete: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
