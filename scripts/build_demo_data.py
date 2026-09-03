#!/usr/bin/env python3
"""Build the tracked one-individual demonstration bundle from full local data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = ROOT / "data"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "demo"
DEFAULT_SOURCE_IID = "HG00436"
DEFAULT_DEMO_IID = "DEMO_HG00436"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-iid", default=DEFAULT_SOURCE_IID)
    parser.add_argument("--demo-iid", default=DEFAULT_DEMO_IID)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def validate_demo_iid(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", value):
        raise ValueError("Demo IID must contain only letters, numbers, underscores, or hyphens.")
    return value


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "gene_importance": output_dir / "all_individuals_gene_importance.csv",
        "open_targets": output_dir / "ot_breast_carcinoma_gene_associations.csv",
        "annotated_info": output_dir / "plot_cache" / "annotated_info.parquet",
        "prs_info": output_dir / "plot_cache" / "prs_info.parquet",
        "full_prs": output_dir / "plot_cache" / "full_prs.parquet",
        "manifest": output_dir / "manifest.json",
    }


def source_paths(source_dir: Path) -> dict[str, Path]:
    return {
        "gene_importance": source_dir / "all_individuals_gene_importance.csv",
        "open_targets": source_dir / "ot_breast_carcinoma_gene_associations.csv",
        "annotated_info": source_dir / "plot_cache" / "annotated_info.parquet",
        "prs_info": source_dir / "plot_cache" / "prs_info.parquet",
        "full_prs": source_dir / "plot_cache" / "full_prs.parquet",
    }


def build_demo_bundle(
    source_dir: Path,
    output_dir: Path,
    source_iid: str,
    demo_iid: str,
    *,
    force: bool = False,
) -> dict:
    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    source_iid = source_iid.strip()
    demo_iid = validate_demo_iid(demo_iid)
    sources = source_paths(source_dir)
    outputs = output_paths(output_dir)

    missing = [str(path) for path in sources.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing source files: " + ", ".join(missing))

    existing = [str(path) for path in outputs.values() if path.exists()]
    if existing and not force:
        raise FileExistsError(
            "Demo output already exists; pass --force to rebuild: " + ", ".join(existing)
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "plot_cache").mkdir(parents=True, exist_ok=True)

    gene_importance = pd.read_csv(sources["gene_importance"], usecols=["Gene", source_iid])
    gene_importance = gene_importance.rename(columns={source_iid: demo_iid})

    open_targets = pd.read_csv(sources["open_targets"])
    open_targets = open_targets.loc[:, [
        column for column in open_targets.columns if not str(column).startswith("Unnamed:")
    ]]

    annotated_info = pd.read_parquet(sources["annotated_info"])
    prs_info = pd.read_parquet(sources["prs_info"], columns=[source_iid])
    prs_info = prs_info.rename(columns={source_iid: demo_iid})
    full_prs = pd.read_parquet(sources["full_prs"]).loc[:, ["IID", "PRS"]].copy()

    if source_iid not in set(full_prs["IID"].astype(str)):
        raise ValueError(f"Source IID {source_iid!r} is absent from full_prs.parquet")
    if len(prs_info) != len(annotated_info):
        raise ValueError("prs_info and annotated_info row counts do not match")

    background_number = 0
    relabeled_iids: list[str] = []
    for iid in full_prs["IID"].astype(str):
        if iid == source_iid:
            relabeled_iids.append(demo_iid)
        else:
            background_number += 1
            relabeled_iids.append(f"BACKGROUND_{background_number:04d}")
    full_prs["IID"] = relabeled_iids

    gene_importance.to_csv(outputs["gene_importance"], index=False)
    open_targets.to_csv(outputs["open_targets"], index=False)
    annotated_info.to_parquet(outputs["annotated_info"], index=False, compression="zstd")
    prs_info.to_parquet(outputs["prs_info"], index=False, compression="zstd")
    full_prs.to_parquet(outputs["full_prs"], index=False, compression="zstd")

    frames = {
        "gene_importance": gene_importance,
        "open_targets": open_targets,
        "annotated_info": annotated_info,
        "prs_info": prs_info,
        "full_prs": full_prs,
    }
    manifest = {
        "schema_version": 1,
        "bundle_id": "xprs-1000g-breast-cancer-demo-hg00436-v1",
        "description": "One-individual XPRS demonstration with a relabeled 1000 Genomes background PRS distribution.",
        "source_cohort": "1000 Genomes Project, East Asian subset",
        "source_iid": source_iid,
        "demo_iid": demo_iid,
        "individual_gene_profiles": 1,
        "background_prs_count": int(len(full_prs) - 1),
        "provenance_note": "The demo IID is a transparent alias for the public source IID, not an anonymization claim.",
        "generated_by": "scripts/build_demo_data.py",
        "source_files": {
            name: {
                "path": str(path.relative_to(source_dir)),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for name, path in sources.items()
        },
        "files": {
            name: {
                "path": str(outputs[name].relative_to(output_dir)),
                "sha256": sha256_file(outputs[name]),
                "bytes": outputs[name].stat().st_size,
                "rows": int(len(frame)),
                "columns": [str(column) for column in frame.columns],
            }
            for name, frame in frames.items()
        },
    }
    outputs["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    args = parse_args()
    manifest = build_demo_bundle(
        args.source_dir,
        args.output_dir,
        args.source_iid,
        args.demo_iid,
        force=args.force,
    )
    print(f"Wrote demo bundle: {args.output_dir.resolve()}")
    print(
        f"Profile: {manifest['demo_iid']} with "
        f"{manifest['background_prs_count']} background PRS values"
    )
    for details in manifest["files"].values():
        print(f"  {details['path']}: {details['bytes']} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
