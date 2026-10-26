# Public cohort data

The complete processed breast-cancer dataset contains 503 East Asian samples
from the 1000 Genomes Project. A public clone uses the tracked
[`demo/`](demo/) profile, which exposes one detailed profile under the alias
`DEMO_HG00436` while retaining a relabeled PRS reference distribution. K-PREDICT
cohort data are private, are not present here, and must never be added to the
public repository.

Private-cohort deployments must use a data root outside this repository. The
root `.gitignore` defensively excludes common private-cohort RDS and rare-finding TSV
filenames, but ignore rules are not an access-control mechanism.

## Recorded upstream inputs

The legacy generation script records these inputs:

- 1000 Genomes Project East Asian genotype data;
- PGS Catalog score `PGS003758` for breast cancer (GRCh37, 46,861 variants);
- breast-cancer association data identified by `MONDO_0007254`; and
- the GPL-licensed XPRS workflow described by Kim and Lee (2025).

Before publishing a downloadable data bundle, confirm the exact 1000 Genomes
release, the exact association-data accession, access dates, and the applicable
terms for every upstream input. PGS Catalog scores must be cited and used under
any restrictions specified by their authors.

## Local files intentionally excluded from Git

- `all_individuals_gene_importance.csv` — per-gene contribution matrix;
- `ot_breast_carcinoma_gene_associations.csv` — Open Targets input;
- `plot_cache/*.parquet` — generated plotting tables; and
- `../r/data.RDS` — legacy XPRS result used to build plotting tables.

These files are generated or derived data, not source code. They remain
available in the working deployment but are ignored by Git until a versioned
distribution archive, checksums, and redistribution statement are prepared.

See [`DATA_ACCESS.md`](../DATA_ACCESS.md) for the bundled demo profile, the
author-request process for the complete processed dataset, and the possible
future Git LFS/release path.

## Required publication metadata

The future data release should provide:

- a stable version and download URL;
- SHA-256 checksums;
- source accessions, genome build, access dates, and citations;
- a description of each transformation from upstream data; and
- a clear statement of the reuse terms that apply to the derived files.
