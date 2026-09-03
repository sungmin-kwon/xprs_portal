#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(data.table)
  library(ggplot2)
  library(ggrepel)
  library(grid)      # for unit() in density plot
})

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 5) {
  stop("Usage: Rscript render_plots.R <patient_id> <rds_path> <fam_path> <out_dir> <base_url_prefix>", call. = FALSE)
}

patient_id <- args[[1]]
rds_path    <- args[[2]]
fam_path    <- args[[3]]  # kept for compatibility
out_dir     <- args[[4]]
base_prefix <- args[[5]]  # unused here, kept for compatibility with your Python call

dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

data <- readRDS(rds_path)

# Source plotting functions (manhattan + density)
# Assumes XPRS_data_plots.R lives next to data.RDS in /r
source(file.path(dirname(rds_path), "XPRS_data_plots.R"), local = TRUE)

# ----------------------------
# 1) BAR PLOT (Top genes) — generated safely without calling plot_topN_genes()
# ----------------------------
# If you truly want to ditch this later, we can update /api/plots + frontend after.
bar_file <- file.path(out_dir, sprintf("%s_bar.png", patient_id))

try({
  PRS_info <- data$PRS_info
  annotated_info <- data$annotated_info
  important_genes <- data$important_genes

  if (!is.data.table(PRS_info)) PRS_info <- as.data.table(PRS_info)
  if (!is.data.table(annotated_info)) annotated_info <- as.data.table(annotated_info)

  if (!patient_id %in% names(PRS_info)) stop(sprintf("Patient '%s' not found in PRS_info.", patient_id))
  if (!all(c("symbol") %in% names(annotated_info))) stop("annotated_info must contain symbol")

  # attributed_value per gene for this patient
  annotated_info[, attributed_value := as.numeric(PRS_info[[patient_id]])]
  df <- annotated_info[is.finite(attributed_value)]
  setorder(df, -attributed_value)

  # filter to important_genes if present
  if (!is.null(important_genes) && nrow(important_genes) > 0 && "Gene" %in% names(important_genes)) {
    df[, clean_symbol := gsub("\\*$", "", as.character(symbol))]
    important_genes[, clean_important_symbol := gsub("\\*$", "", as.character(Gene))]
    df <- df[clean_symbol %in% important_genes$clean_important_symbol]
    df <- df[!duplicated(clean_symbol)]
    df[, clean_symbol := NULL]
  }

  # Choose top 10% by default to mimic your UI label; change if you want
  gene.threshold <- 10
  topN <- max(1, round(nrow(df) * gene.threshold / 100))
  df <- df[1:topN]

  # Build bar plot
  df[, symbol := as.character(symbol)]
  p_bar <- ggplot(df, aes(x = attributed_value, y = reorder(symbol, attributed_value), fill = attributed_value)) +
    geom_bar(stat = "identity", width = 0.8) +
    theme_minimal() +
    labs(
      title = paste("Top", topN, "Genes (Individual:", patient_id, ")"),
      x = "Attributed Value of Gene (%)",
      y = "Gene"
    ) +
    theme(
      axis.text.y = element_text(size = 8),
      axis.title = element_text(size = 12),
      plot.title = element_text(size = 14, face = "bold")
    ) +
    scale_fill_gradient(low = "lightblue", high = "darkblue")

  ggsave(bar_file, p_bar, width = 8, height = 6, dpi = 160)
}, silent = TRUE)

# If bar plot failed for any reason, still continue; /api/plots will catch missing file.
# (You can change this behavior later.)

# ----------------------------
# 2) Manhattan PNG
# ----------------------------
man_file <- file.path(out_dir, sprintf("%s_manhattan.png", patient_id))
p_manhattan <- plot_manhattan_individual(data, patient_id, top_n = 10, use_midpoint = TRUE)
ggsave(man_file, p_manhattan, width = 12, height = 5, dpi = 160)

# ----------------------------
# 3) Density PNG
# ----------------------------
den_file <- file.path(out_dir, sprintf("%s_density.png", patient_id))
p_density <- plot_prs_density(data, patient_id, label_digits = 2)
ggsave(den_file, p_density, width = 8, height = 5, dpi = 160)

cat("OK\n")