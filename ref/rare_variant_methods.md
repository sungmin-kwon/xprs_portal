# Rare-Variant Track Methods Note

## Citation
K-PREDICT rare-variant findings supplied with the data handoff, as imported by the XPRS portal (import contract: `docs/private-cohort-onboarding.md`). This note describes the rare-variant track shown in the portal's Rare Variant Analysis panel. It is separate from the polygenic risk score (PRS) and from XPRS gene contributions.

## Source Scope
This note explains how the supplied rare-variant findings were defined and labelled, and which fields the portal shows for each finding. It contains no individual-level findings. The chat cannot see any individual's rare-variant findings; they are shown only in the Rare Variant Analysis panel.

## Relationship to the PRS
- The PRS and XPRS gene contributions summarize many common variants. The rare-variant track lists individual rare variants classified as pathogenic or likely pathogenic.
- The two evidence types are shown side by side and are never combined into one score.
- A gene can appear in both: for example, a gene may contribute very little to the common-variant PRS and still carry a rare pathogenic finding in the rare-variant track.

## Which Findings Are Included
- Every supplied finding carries a ClinVar classification of pathogenic (P) or likely pathogenic (LP), with its ClinVar review level (stars) shown in the panel.
- The supplied data record ClinVar classifications. No independent re-classification under ACMG/AMP criteria is recorded in the supplied data.
- All supplied findings are marked as passing the supplier's quality control; the supplied data do not include variant allele fraction or an assessment of somatic origin (for example clonal haematopoiesis), so germline versus somatic origin cannot be judged from these fields.

## Disease Assignment
- `track=panel` findings were mapped to an XPRS disease by gene membership in Genomics England PanelApp GREEN panels for that disease.
- PanelApp has no dedicated coronary artery disease or myocardial infarction panel, so the supplied pipeline uses the Familial hypercholesterolaemia panel as the closest monogenic analogue; these two diseases therefore share the same rare-variant gene set.
- `track=other` findings have no validated XPRS disease assignment. The portal shows them separately as "Other findings" and never assigns a disease from free-text ClinVar condition names.
- The same variant can be listed under several diseases when its gene belongs to several disease panels. These rows are intentional: they describe one variant in one person, interpreted separately per disease panel, and the inheritance interpretation (alert or carrier) can differ between panels. They should not be counted as independent findings.

## Alert and Carrier Labels
The supplied pipeline labelled each finding using PanelApp and ClinGen modes of inheritance, and the portal keeps those labels unchanged. The supplied reason for each label is shown in the panel as "Why this classification".
- **Alert**: a finding where one copy is considered sufficient, designated for prominent review. In the supplied data this applies when PanelApp lists the gene as monoallelic (≈ autosomal dominant), when PanelApp lists both modes and ClinGen curates the gene as autosomal dominant or semidominant, or when ClinGen curates the gene as dominant or semidominant without a PanelApp GREEN panel.
- **Carrier**: a heterozygous finding in a gene interpreted as recessive, which generally indicates carrier status rather than disease. In the supplied data this applies when PanelApp lists the gene as biallelic (≈ autosomal recessive), when ClinGen curates only recessive inheritance, when PanelApp lists both modes and ClinGen has no curation, or when neither PanelApp nor ClinGen provides a curation.
- An alert is not a diagnosis, and a carrier label is not a disease finding.

## Fields Shown for Each Finding
The Rare Variant Analysis panel shows, for each finding: gene, HGVS and genomic variant, dbSNP ID, genotype, molecular consequence and consequence class, ClinVar classification, ClinVar review level, confidence tier, ClinVar condition(s), finding category, PanelApp inheritance and panel count, ClinGen inheritance, evidence tier and detail, the supplied classification reason, cohort allele frequency, gnomAD allele frequency, gnomAD East Asian frequency, and an East Asian frequency context category (East-Asian-specific, East-Asian-enriched, not East-Asian-specific, absent in gnomAD, or no data). The thresholds behind the East Asian context categories are not documented in the supplied data.

## Versions and Updates
- The imported release is identified by its handoff date (2026-09-17).
- The supplied data do not record which ClinVar or PanelApp versions were used.
- The portal does not re-check findings against newer ClinVar or PanelApp releases and does not send notifications if a variant is reclassified.

## Interpretation Boundaries
- These are supplied research annotations. They do not establish a diagnosis, prognosis, or a causal relationship with the selected disease.
- Decisions about confirmatory testing, family testing, or clinical action are outside the scope of this portal.
