library(dplyr)
library(tidyr)
library(readr)
library(data.table)
library(ggplot2)
library(ggrepel)

get_person_attributed_value_and_prs <- function(RDS.file, person) {
  PRS_info <- data$PRS_info
  annotated_info <- data$annotated_info
  full_prs <- data$full_prs
  important_genes <- data$important_genes
  
  '%notin%' <- Negate('%in%')
  
  # Convert to data.table if not already
  if (!is.data.table(PRS_info)) setDT(PRS_info)
  if (!is.data.table(annotated_info)) setDT(annotated_info)
  
  PRS_info$Gene <- annotated_info$symbol
  annotated_info$attributed_value <- PRS_info[[person]]
  df <- annotated_info[order(annotated_info$attributed_value, decreasing = T), ]
  
  # Step 1: Clean the symbol in df by removing trailing * but leave the original symbol intact
  df$clean_symbol <- gsub("\\*$", "", df$symbol)
  
  # Step 2: Clean the symbols in important_genes by removing trailing *
  important_genes$clean_important_symbol <- gsub("\\*$", "", important_genes$Gene)
  
  # Step 3: Now filter df using the cleaned symbols from important_genes
  df <- df[df$clean_symbol %in% important_genes$clean_important_symbol]
  
  # Step 4: Remove duplicates based on the cleaned symbol (not the original one)
  df <- df[!duplicated(df$clean_symbol), ]
  
  # Step 5: Remove the clean_symbol column if it's no longer needed
  df$clean_symbol <- NULL
  
  prs <- full_prs$PRS[full_prs$IID == person]
  
  return(list(df = df, prs = prs))
}

plot_topN_genes <- function(data, person, gene.threshold = 10) {
  df <- get_person_attributed_value_and_prs(data, person)$df
  topN <- round(nrow(df) * gene.threshold/100)
  df <- df[1:topN]
  df <- df %>% arrange(desc(attributed_value))
  
  ggplot(df, aes(x = attributed_value, y = reorder(symbol, attributed_value), fill=attributed_value)) +
    geom_bar(stat = "identity", width = 0.8) +
    theme_minimal() +
    labs(title = paste("Top", topN, "Genes (Individual:", person, ")"),
         x = "Attributed Value of Gene (%)",
         y = "Gene") +
    theme(axis.text.y = element_text(size = 8),
          axis.title = element_text(size = 12),
          plot.title = element_text(size = 16, face = "bold")) +
    scale_fill_gradient(low = "lightblue", high = "darkblue") +
    xlim(0, max(df$attributed_value) * 1.1)
}

plot_manhattan_individual <- function(data, person, top_n = 10, use_midpoint = TRUE) {
  ann <- as.data.table(data$annotated_info)
  prs <- as.data.table(data$PRS_info)
  
  if (!person %in% names(prs)) stop(sprintf("Person '%s' not found in PRS_info.", person))
  if (!all(c("chr","symbol","start","end") %in% names(ann))) {
    stop("annotated_info must contain chr, symbol, start, end.")
  }
  
  ann[, BP := if (use_midpoint) (as.numeric(start) + as.numeric(end))/2 else as.numeric(start)]
  
  ann[, CHR := gsub("^chr", "", as.character(chr), ignore.case = TRUE)]
  ann <- ann[CHR %in% as.character(1:22)]
  ann[, CHR := as.integer(CHR)]
  ann <- ann[!is.na(BP) & !is.na(CHR)]
  
  if (nrow(prs) != nrow(ann)) {
    stop("Row counts differ between PRS_info and annotated_info; need a symbol-based merge.")
  }
  ann[, ATTR := as.numeric(prs[[person]])]
  ann <- ann[!is.na(ATTR)]
  
  setorder(ann, CHR, BP)
  chr_sizes <- ann[, .(chr_len = max(BP, na.rm = TRUE)), by = CHR][order(CHR)]
  chr_sizes[, chr_start := c(0, head(cumsum(as.numeric(chr_len)), -1))]
  ann <- merge(ann, chr_sizes[, .(CHR, chr_start)], by = "CHR", all.x = TRUE)
  ann[, x := BP + chr_start]
  
  chr_centers <- ann[, .(center = (min(x) + max(x))/2), by = CHR][order(CHR)]
  
  ann <- ann[!is.na(ATTR)]
  setorder(ann, -ATTR)
  top_dt <- ann[1:min(top_n, .N)]
  setorder(ann, ATTR)
  bot_dt <- ann[1:min(top_n, .N)]
  
  ann[, category := "Other"]
  ann[ top_dt,  category := "Top",    on = .(CHR, BP, symbol, ATTR, x) ]
  ann[ bot_dt,  category := "Bottom", on = .(CHR, BP, symbol, ATTR, x) ]
  
  ggplot(ann, aes(x = x, y = ATTR)) +
    geom_point(aes(color = category), size = 1, alpha = 0.8) +
    geom_hline(yintercept = 0, linewidth = 0.3, alpha = 0.6) +
    scale_x_continuous(breaks = chr_centers$center, labels = chr_centers$CHR) +
    scale_color_manual(values = c(Top="red", Bottom="blue", Other="grey70")) +
    labs(
      title = sprintf("Gene-based Manhattan Plot (Individual: %s)", person),
      x = "Chr",
      y = "Attributed Value of Gene",
      color = NULL
    ) +
    ggrepel::geom_text_repel(
      data = rbind(top_dt, bot_dt),
      aes(label = symbol),
      size = 4,
      max.overlaps = Inf,
      box.padding = 0.3,
      point.padding = 0.2,
      show.legend = FALSE
    ) +
    theme_bw() +
    theme(panel.grid.major.x = element_blank(),
          panel.grid.minor.x = element_blank(),
          plot.title = element_text(hjust = 0.5, size = 20),
          axis.title = element_text(size=13))
}

plot_prs_density <- function(
    data,
    person,
    label_digits = 2,
    arrow_y = 0.6,
    text_y  = 0.65
) {
  if (!all(c("IID","PRS") %in% names(data$full_prs))) {
    stop("data$full_prs must contain columns: IID, PRS")
  }
  
  prs_all <- data$full_prs$PRS
  prs_all <- prs_all[is.finite(prs_all)]
  
  prs_value <- data$full_prs$PRS[data$full_prs$IID == person]
  if (length(prs_value) != 1 || !is.finite(prs_value)) {
    stop("Invalid PRS value for individual")
  }
  
  pct <- mean(prs_all <= prs_value)
  label_txt <- sprintf("Bottom %.*f %%", label_digits, pct * 100)
  
  d <- density(prs_all, na.rm = TRUE)
  ddf <- data.frame(x = d$x, y = d$y)
  
  library(ggplot2)
  
  ggplot(ddf, aes(x = x, y = y)) +
    geom_line(linewidth = 0.9) +
    geom_segment(aes(x = prs_value, xend = prs_value, y = 0, yend = max(ddf$y) * arrow_y),
                 arrow = arrow(length = unit(0.25, "cm")),
                 color = "red", linewidth = 0.7) +
    annotate("text", x = prs_value, y = max(ddf$y) * text_y, label = label_txt,
             color = "red", size = 5, fontface = "bold", vjust = -0.5) +
    labs(title = sprintf("Individual Risk in Cohort Density Plot (%s)", person),
         x = "PRS", y = "Density") +
    theme_classic() +
    theme(plot.title = element_text(hjust = 0.5, size = 16, face = "bold"))
}

# ------------------------------------------------------------
# NEW: JSON-ready data exporters for Plotly.js
# ------------------------------------------------------------

manhattan_plot_data <- function(data, person, use_midpoint = TRUE) {
  ann <- as.data.table(data$annotated_info)
  prs <- as.data.table(data$PRS_info)
  
  if (!person %in% names(prs)) stop(sprintf("Person '%s' not found in PRS_info.", person))
  if (!all(c("chr","symbol","start","end") %in% names(ann))) {
    stop("annotated_info must contain chr, symbol, start, end.")
  }
  
  ann[, BP := if (use_midpoint) (as.numeric(start) + as.numeric(end))/2 else as.numeric(start)]
  ann[, CHR := gsub("^chr", "", as.character(chr), ignore.case = TRUE)]
  ann <- ann[CHR %in% as.character(1:22)]
  ann[, CHR := as.integer(CHR)]
  ann <- ann[!is.na(BP) & !is.na(CHR)]
  
  if (nrow(prs) != nrow(ann)) {
    stop("Row counts differ between PRS_info and annotated_info; need a symbol-based merge.")
  }
  
  ann[, ATTR := as.numeric(prs[[person]])]
  ann <- ann[is.finite(ATTR)]
  
  setorder(ann, CHR, BP)
  
  chr_sizes <- ann[, .(chr_len = max(BP, na.rm = TRUE)), by = CHR][order(CHR)]
  chr_sizes[, chr_start := c(0, head(cumsum(as.numeric(chr_len)), -1))]
  ann <- merge(ann, chr_sizes[, .(CHR, chr_start)], by = "CHR", all.x = TRUE)
  ann[, x := BP + chr_start]
  
  chr_centers <- ann[, .(center = (min(x) + max(x))/2), by = CHR][order(CHR)]
  
  points <- ann[, .(
    gene = as.character(symbol),
    chr  = as.integer(CHR),
    pos  = as.numeric(BP),
    x    = as.numeric(x),
    variance = as.numeric(ATTR)
  )]
  
  list(
    points = points,
    chr_centers = chr_centers[, .(chr = as.integer(CHR), center = as.numeric(center))],
    title = sprintf("Gene-based Manhattan Plot (Individual: %s)", person),
    y_label = "Variance of Gene Contribution Score"
  )
}

prs_density_data <- function(data, person, label_digits = 2) {
  if (!all(c("IID","PRS") %in% names(data$full_prs))) {
    stop("data$full_prs must contain columns: IID, PRS")
  }

  prs_all <- data$full_prs$PRS
  prs_all <- prs_all[is.finite(prs_all)]

  prs_value <- data$full_prs$PRS[data$full_prs$IID == person]
  if (length(prs_value) != 1 || !is.finite(prs_value)) {
    stop("Invalid PRS value for individual")
  }

  pct <- mean(prs_all <= prs_value)
  label_txt <- sprintf("Bottom %.*f %%", label_digits, pct * 100)

  d <- density(prs_all, na.rm = TRUE)

  list(
    density = list(x = as.numeric(d$x), y = as.numeric(d$y)),

    # individual marker
    prs_value = as.numeric(prs_value),
    percentile = as.numeric(pct),
    label = label_txt,

    # NEW: cohort PRS values for interactive percentile-at-cursor
    cohort_prs = as.numeric(prs_all),

    title = sprintf("Individual Risk in Cohort Density Plot (%s)", person),
    x_label = "PRS",
    y_label = "Density"
  )
}