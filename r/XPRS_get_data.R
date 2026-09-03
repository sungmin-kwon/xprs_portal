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
  df$clean_symbol <- gsub("\\*+$", "", df$symbol)  # Remove trailing * from df$symbol
  
  # Step 2: Merge df with important_genes on the cleaned df$symbol and important_genes$MAPPED_GENE
  df <- merge(df, important_genes[, c("MAPPED_GENE", "P_VALUE")], 
              by.x = "clean_symbol", by.y = "MAPPED_GENE", all.x = TRUE)
  
  # Step 3: Sort first by attributed_value and then by P_VALUE
  df <- df[order(-df$attributed_value, df$P_VALUE), ]
  df_filtered <- df[df$within_region_rank_by_variance == 1, ]
  df_filtered <- df_filtered %>% distinct()
  
  df <- df_filtered
  df <- df[, c("clean_symbol", "attributed_value")]
  names(df) <- c("Gene", "Attributed_Value_of_Gene")
  
  # Get the PRS value for the specific person
  prs_value <- full_prs[full_prs$IID == person, ]$PRS
  
  # Return both objects as a list
  return(list(attributed_values = df, prs = prs_value))
}

plot_manhattan_variance <- function(data, top_n_label = 15) {
  annotated_info <- as.data.table(data$annotated_info)
  
  # Keep only scalar columns (NO list-cols)
  df <- annotated_info[
    within_region_rank_by_variance == 1,
    .(chr, start, end, symbol, variance)
  ]
  
  df <- unique(df)
  df <- df[order(chr, start)]
  
  # Chromosome lengths + cumulative coordinate (avoid integer overflow)
  chr_sizes <- df[, .(chr_len = as.numeric(max(end, na.rm = TRUE))), by = chr][order(chr)]
  chr_sizes[, chr_start := c(0, head(cumsum(chr_len), -1))]
  
  df <- merge(df, chr_sizes[, .(chr, chr_start)], by = "chr", all.x = TRUE)
  df[, BPcum := as.numeric(start) + chr_start]
  
  axis_df <- df[, .(center = (min(BPcum) + max(BPcum)) / 2), by = chr]
  
  # Top labels by variance
  top_df <- df[order(-variance)][1:min(top_n_label, .N)]
  top_df[, clean_symbol := gsub("\\*+$", "", symbol)]
  
  ggplot(df, aes(x = BPcum, y = variance, color = as.factor(chr))) +
    geom_point(alpha = 0.7, size = 0.8) +
    scale_x_continuous(breaks = axis_df$center, labels = axis_df$chr) +
    labs(
      x = "Chromosome",
      y = "Variance of Gene Contribution Score",
      title = "Population Manhattan Plot"
    ) +
    theme_bw() +
    theme(
      legend.position = "none",
      plot.title = element_text(hjust = 0.5, size = 24),
      axis.title = element_text(size=13)
    ) +
    geom_text_repel(
      data = top_df,
      aes(x = BPcum, y = variance, label = clean_symbol),
      size = 4,
      inherit.aes = FALSE,
      max.overlaps = Inf
    )
}

plot_manhattan_individual <- function(data, person, top_n = 10, use_midpoint = TRUE) {
  ann <- as.data.table(data$annotated_info)
  prs <- as.data.table(data$PRS_info)
  
  if (!person %in% names(prs)) stop(sprintf("Person '%s' not found in PRS_info.", person))
  if (!all(c("chr","symbol","start","end") %in% names(ann))) {
    stop("annotated_info must contain chr, symbol, start, end.")
  }
  
  # --- create gene position (BP) ---
  ann[, BP := if (use_midpoint) (as.numeric(start) + as.numeric(end))/2 else as.numeric(start)]
  
  # keep autosomes only and coerce chr to integer 1..22
  ann[, CHR := gsub("^chr", "", as.character(chr), ignore.case = TRUE)]
  ann <- ann[CHR %in% as.character(1:22)]
  ann[, CHR := as.integer(CHR)]
  ann <- ann[!is.na(BP) & !is.na(CHR)]
  
  # --- attach individual's attributed values (row-aligned) ---
  if (nrow(prs) != nrow(ann)) {
    stop("Row counts differ between PRS_info and annotated_info; need a symbol-based merge.")
  }
  ann[, ATTR := as.numeric(prs[[person]])]
  ann <- ann[!is.na(ATTR)]
  
  # --- cumulative x for Manhattan-style layout ---
  setorder(ann, CHR, BP)
  chr_sizes <- ann[, .(chr_len = max(BP, na.rm = TRUE)), by = CHR][order(CHR)]
  chr_sizes[, chr_start := c(0, head(cumsum(as.numeric(chr_len)), -1))]
  ann <- merge(ann, chr_sizes[, .(CHR, chr_start)], by = "CHR", all.x = TRUE)
  ann[, x := BP + chr_start]
  
  chr_centers <- ann[, .(center = (min(x) + max(x))/2), by = CHR][order(CHR)]
  
  # --- pick top/bottom by ATTR safely ---
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
    scale_color_manual(values = c(Top="red", Bottom="blue", Other="grey70"),
                       breaks = c("Top", "Bottom")) +
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
          plot.title = element_text(hjust = 0.5, size = 24),
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
  
  # Bottom X%
  pct <- mean(prs_all <= prs_value)
  label_txt <- sprintf("Bottom %.*f %%", label_digits, pct * 100)
  
  # TRUE density (no normalization)
  d <- density(prs_all, na.rm = TRUE)
  ddf <- data.frame(x = d$x, y = d$y)
  
  library(ggplot2)
  
  ggplot(ddf, aes(x = x, y = y)) +
    geom_line(linewidth = 0.9) +
    
    # vertical arrow from baseline up to fixed y
    annotate(
      "segment",
      x = prs_value, xend = prs_value,
      y = 0,         yend = arrow_y,
      colour = "red", linewidth = 1.0,
      arrow = arrow(type = "closed", length = unit(0.25, "cm"))
    ) +
    
    # label above arrow
    annotate(
      "text",
      x = prs_value,
      y = text_y,
      label = label_txt,
      colour = "red",
      fontface = "bold",
      size = 7,
      vjust = 0
    ) +
    
    # 👇 THIS is the only axis change you wanted
    scale_y_continuous(limits = c(0, 1)) +
    
    labs(
      title = sprintf("Individual Risk in Cohort Density Plot (%s)", person),
      x = "PRS",
      y = "Density"
    ) +
    theme_minimal(base_size = 16) +
    theme(
      panel.border = element_rect(color = "black", fill = NA, linewidth = 1),
      plot.title = element_text(hjust = 0.5, size = 24),
      axis.title = element_text(size=14)
    )
}


# cohort.genotype.file : path/to/EASID_1000G_plink (East Asian 1000 Genomes subset)
# PRS.scoring.file : downloaded from https://www.pgscatalog.org/score/PGS003758/ (east asian (Japanese); breast cancer; P+T)
# GWAS.association.file : https://www.ebi.ac.uk/gwas/efotraits/MONDO_0007254 (breast cancer)

# 위의 파일들 가지고 breast cancer XPRS run 해서 나온 RDS file: data.RDS
data <- readRDS("data.RDS") # 경로설정 다시 해야함
# head(data, n=5)

# cohort.genotype.file fam (iid 가지고 와서 읽을수 있도록) 한 파일 : EASID_1000G_plink
fam <- fread("EASID_1000G_plink.fam") # 경로설정 다시 해야함
head(fam)

#fam$V1[n] <- 여기서 n을 변경시키면 됨, 혹은 head(fam) 하면 볼수 있듯 V1 에서의 iid "HG00403" 으로 입력해서 가지고 올수 있음 
get_person_attributed_value_and_prs(data, fam$V1[1])
get_person_attributed_value_and_prs(data, "HG00403")

# p1 <- plot_manhattan_variance(data, top_n_label = 10)
# print(p1)

# p2 <- plot_manhattan_individual(data, "HG00436", top_n = 10)
# print(p2)

p3 <- plot_prs_density(data, "HG00436")
print(p3)
