# Bundled demonstration profile

This directory contains the small, repository-tracked data profile used by a
fresh XPRS Portal clone.

`DEMO_HG00436` is a transparent display alias for the public 1000 Genomes sample
`HG00436`. Its gene- and region-level XPRS contribution values are unchanged.
The alias is intended to distinguish the bundled demonstration from a complete
cohort installation; it is not presented as anonymization.

Only this individual's detailed contribution columns are included. The density
plot still needs a reference distribution, so `full_prs.parquet` retains the
503 processed PRS values while replacing all other sample identifiers with
generic `BACKGROUND_####` labels.

The Open Targets table is not individual-level data and is shared with the full
profile. See [`../README.md`](../README.md) for upstream sources, reuse checks,
and the full processed-data policy.

## Files

- `all_individuals_gene_importance.csv` — 6,500 genes for `DEMO_HG00436`;
- `plot_cache/prs_info.parquet` — region contributions for the demo individual;
- `plot_cache/annotated_info.parquet` — genomic region annotations;
- `plot_cache/full_prs.parquet` — relabeled 503-value PRS reference distribution;
- `ot_breast_carcinoma_gene_associations.csv` — Open Targets associations; and
- `manifest.json` — checksums, row counts, columns, and source-file checksums.

Regenerate the bundle from the full local data with:

```bash
python scripts/build_demo_data.py --force
```
