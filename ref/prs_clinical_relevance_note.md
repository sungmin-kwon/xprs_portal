# Polygenic Risk Score Clinical Relevance Note

## Citation
Kim NY, Lee H, Kim S, Kim YJ, Lee H, Lee J, Kwak SH, Lee S. *The clinical relevance of a polygenic risk score for type 2 diabetes mellitus in the Korean population*. Scientific Reports. 2024;14:5749. doi:10.1038/s41598-024-55313-0.

## Source Scope
This note is a curated summary derived from the cited open-access article. It focuses on core PRS concepts, how the paper constructed and evaluated a PRS, and what kinds of clinical interpretation the authors support.

## What a PRS Is
A polygenic risk score (PRS) summarizes inherited susceptibility to a complex trait or disease by aggregating the effects of many genetic variants. In the paper's framing, a PRS is built from genome-wide association study (GWAS) results and is intended to quantify individual genetic susceptibility rather than provide a diagnosis by itself.

The paper describes PRS conceptually as:
- a weighted aggregation of risk alleles
- derived from GWAS-identified variants
- useful for stratifying individuals into relatively higher- and lower-genetic-risk groups

## Why This Paper Matters
The paper is not about XPRS specifically. Instead, it addresses a foundational question relevant to XPRS:
- whether a disease-specific PRS has meaningful clinical or prognostic value in a real longitudinal cohort

This is useful background because XPRS is an interpretability layer built on top of a PRS. To explain XPRS well, it helps to understand what the underlying PRS is intended to do and how it is evaluated clinically.

## Study Goal
The authors aimed to evaluate the clinical relevance of a type 2 diabetes mellitus (T2DM) PRS in an East Asian, specifically Korean, population.

They explicitly asked whether a T2DM PRS could help predict:
- overall T2DM incidence
- progression from normal glucose tolerance to prediabetes
- progression from prediabetes to T2DM
- disease severity, including later insulin treatment

## Data Sources and Cohorts
The PRS was built and evaluated using Korean and East Asian datasets:
- KoGES_HEXA for a Korean GWAS
- Biobank Japan GWAS summary statistics
- KoGES_CAVAS for validation and hyperparameter selection
- KoGES Ansan and Ansung longitudinal cohort for long-term evaluation
- UK Biobank East Asian samples for external validation

The East Asian GWAS meta-analysis used for PRS training included:
- 269,487 total samples
- 44,315 cases
- 225,172 controls

The main longitudinal evaluation used:
- 5,490 participants from KoGES Ansan and Ansung
- baseline plus repeated follow-up over approximately 14 to 16 years

## How the PRS Was Constructed
The paper compared two genome-wide PRS construction methods:
- Lassosum
- PRS-CS

Both methods use GWAS summary statistics and reference panels to account for linkage disequilibrium (LD).

Key points from the Methods:
- the GWAS was performed in KoGES_HEXA using a linear mixed model
- the Korean GWAS results were meta-analyzed with Biobank Japan T2DM GWAS results
- the LD reference panel used East Asian individuals
- Lassosum used an additional validation dataset for hyperparameter tuning
- Lassosum slightly outperformed PRS-CS in the PRS-only model and was used for the main study analyses

## How the PRS Was Used in Analysis
The paper evaluated PRS in two main ways:

1. Categorized PRS
   - bottom decile
   - middle 10-90%
   - top decile

2. Standardized PRS
   - treated as a continuous-scale predictor

The categorized PRS supports clinically intuitive risk stratification, while the standardized PRS supports more conventional statistical modeling.

## What the Paper Found
The study reports that a higher T2DM PRS was associated with:
- greater cumulative prevalence of T2DM
- greater progression from non-diabetes to T2DM
- greater progression from normal glucose tolerance to prediabetes
- greater progression from prediabetes to T2DM
- greater likelihood of insulin prescription among T2DM patients
- association with a more severe diabetes subgroup characterized by insulin resistance and beta-cell dysfunction

Examples reported in the paper include:
- top-decile PRS group had much higher baseline T2DM prevalence than the bottom-decile group
- hazard ratio for top versus middle PRS group in non-diabetes to T2DM progression was 1.91
- hazard ratio for top versus middle PRS group in progression from prediabetes to T2DM was 1.64
- top-decile PRS group had significantly greater likelihood of insulin prescription

## Clinical Interpretation
The paper supports a careful clinical interpretation of PRS:
- PRS can improve risk stratification
- PRS may add prognostic information beyond some standard clinical variables
- PRS may help identify higher-risk individuals earlier
- PRS may help identify subgroups with more severe disease biology

But the paper does **not** frame PRS as a standalone replacement for clinical assessment.

The authors explicitly state that PRS should not be considered an alternative to traditional clinical risk factors, but rather a possible addition.

## Prediction Models
The authors evaluated a series of Cox regression models that added PRS to increasing levels of clinical covariates.

These models included combinations of:
- sex
- age
- family history
- BMI
- systolic blood pressure
- smoking status
- HDL
- LDL
- triglycerides

The paper reports that models including PRS achieved significantly better Harrell's C-indices than corresponding models without PRS.

## Interpretation Boundaries
Important caveats from the paper:
- the PRS was developed and evaluated in East Asian populations, so ancestry matters
- PRS performance is not universally portable across populations
- the PRS is useful as a supplement, not a replacement, for established clinical risk factors
- the study had limitations in phenotype detail, including lack of some tests such as C-peptide or diabetes autoantibody measurements
- some endpoints, such as diabetic complications, were not predicted as strongly as incidence or insulin prescription

## Relevance to XPRS
This paper is useful background for XPRS because it clarifies what the underlying PRS is doing before interpretability is added.

In that sense:
- the PRS provides the disease-risk signal
- XPRS explains which genes, regions, and SNPs are contributing to that signal

So this paper is better treated as:
- a PRS theory / clinical utility reference
- not an XPRS methodology paper

## High-Confidence Facts From the Paper
- The paper focuses on T2DM PRS clinical utility in a Korean / East Asian population.
- It uses East Asian GWAS meta-analysis data for PRS training.
- It compares Lassosum and PRS-CS and uses Lassosum for the main analyses.
- It uses both categorized PRS and standardized PRS.
- Higher PRS is associated with greater risk of T2DM progression.
- Higher PRS is associated with greater likelihood of insulin treatment.
- Adding PRS improves prediction metrics beyond models without PRS.
- The paper explicitly argues that PRS should complement, not replace, traditional clinical risk factors.

## Suggested Use in the Portal
This note is a good background reference for follow-up questions such as:
- What is a polygenic risk score?
- How is a PRS typically constructed?
- What does it mean clinically if someone has a high PRS?
- Should PRS replace standard clinical risk factors?
- Why does ancestry matter in PRS interpretation?

It should not be treated as the main source for:
- XPRS-specific formulas
- XPRS-specific gene contribution definitions
- XPRS visualization logic

Those questions should still be answered primarily from [`xprs_methods.md`](xprs_methods.md).
