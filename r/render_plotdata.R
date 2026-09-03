#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(data.table)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 5) {
  stop("Usage: Rscript render_plots.R <patient_id> <rds_path> <fam_path> <out_dir> <base_url_prefix>", call. = FALSE)
}

patient_id <- args[[1]]
rds_path    <- args[[2]]
fam_path    <- args[[3]]  # kept for compatibility / optional validation
out_dir     <- args[[4]]
base_prefix <- args[[5]]  # e.g. "/static/plots" (for URLs)

dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

data <- readRDS(rds_path)

source(file.path(dirname(rds_path), "XPRS_data_plots.R"), local = TRUE)

# --- Build JSON-ready data ---
manhattan <- manhattan_plot_data(data, patient_id, use_midpoint = TRUE)
density   <- prs_density_data(data, patient_id, label_digits = 2)

# --- Deterministic filenames ---
man_file <- file.path(out_dir, sprintf("%s_manhattan.json", patient_id))
den_file <- file.path(out_dir, sprintf("%s_density.json", patient_id))

# --- Save JSON (overwrite if exists) ---
write_json(manhattan, man_file, auto_unbox = TRUE, digits = NA)
write_json(density,   den_file, auto_unbox = TRUE, digits = NA)

# --- Emit small manifest JSON ---
cat(
  toJSON(
    list(
      manhattan_url = file.path(base_prefix, basename(man_file)),
      density_url   = file.path(base_prefix, basename(den_file))
    ),
    auto_unbox = TRUE
  ),
  "\n"
)