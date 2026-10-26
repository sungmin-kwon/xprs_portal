#!/usr/bin/env python3
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from config import APP_BASE_DIR, PLOT_DATA_CACHE_DIR


DEFAULT_RDS_PATH = APP_BASE_DIR / "r" / "data.RDS"
PARQUET_FILENAMES = {
    "annotated_info": "annotated_info.parquet",
    "prs_info": "prs_info.parquet",
    "full_prs": "full_prs.parquet",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Python-native Parquet plot caches from the legacy R data.RDS file."
    )
    parser.add_argument(
        "--rds-path",
        type=Path,
        default=DEFAULT_RDS_PATH,
        help=f"Path to the source RDS file (default: {DEFAULT_RDS_PATH})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PLOT_DATA_CACHE_DIR,
        help=f"Directory for generated Parquet files (default: {PLOT_DATA_CACHE_DIR})",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep the intermediate exported CSV files for debugging.",
    )
    return parser.parse_args()


def write_r_export_script(script_path: Path) -> None:
    script = """\
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript export_plot_tables.R <rds_path> <out_dir>", call. = FALSE)
}

rds_path <- args[[1]]
out_dir <- args[[2]]
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

x <- readRDS(rds_path)

write.csv(
  x$annotated_info[, c("chr", "symbol", "start", "end")],
  gzfile(file.path(out_dir, "annotated_info.csv.gz")),
  row.names = FALSE
)
write.csv(
  x$PRS_info,
  gzfile(file.path(out_dir, "prs_info.csv.gz")),
  row.names = FALSE
)
write.csv(
  x$full_prs,
  gzfile(file.path(out_dir, "full_prs.csv.gz")),
  row.names = FALSE
)
"""
    script_path.write_text(script, encoding="utf-8")


def export_rds_to_csv(rds_path: Path, temp_dir: Path) -> None:
    if not rds_path.exists():
        raise FileNotFoundError(f"RDS file not found: {rds_path}")

    rscript_path = shutil.which("Rscript")
    if not rscript_path:
        raise RuntimeError("Rscript is not available on PATH.")

    export_script = temp_dir / "export_plot_tables.R"
    write_r_export_script(export_script)

    subprocess.run(
        [rscript_path, str(export_script), str(rds_path), str(temp_dir)],
        check=True,
        capture_output=True,
        text=True,
    )


def convert_csv_exports_to_parquet(temp_dir: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    mappings = {
        stem: out_dir / filename
        for stem, filename in PARQUET_FILENAMES.items()
    }

    for stem, out_path in mappings.items():
        csv_path = temp_dir / f"{stem}.csv.gz"
        if not csv_path.exists():
            raise FileNotFoundError(f"Expected intermediate export missing: {csv_path}")

        df = pd.read_csv(csv_path)
        df.to_parquet(out_path, index=False)
        print(f"Wrote {out_path} with shape {df.shape}")


def main() -> int:
    args = parse_args()

    with tempfile.TemporaryDirectory(prefix="xprs_plot_export_") as tmp:
        temp_dir = Path(tmp)
        try:
            export_rds_to_csv(args.rds_path, temp_dir)
            convert_csv_exports_to_parquet(temp_dir, args.out_dir)

            if args.keep_temp:
                kept_dir = args.out_dir / "csv_exports"
                kept_dir.mkdir(parents=True, exist_ok=True)
                for csv_path in temp_dir.glob("*.csv.gz"):
                    shutil.copy2(csv_path, kept_dir / csv_path.name)
                print(f"Copied intermediate CSV exports to {kept_dir}")

            print("Parquet cache build complete.")
            return 0
        except subprocess.CalledProcessError as exc:
            sys.stderr.write(exc.stderr or str(exc))
            return exc.returncode or 1
        except Exception as exc:
            sys.stderr.write(f"{exc}\n")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
