# Data access

XPRS Portal supports two data profiles. Neither profile contains KFDA cohort
data.

## Bundled public demonstration

The repository includes `data/demo/`, a directly runnable profile containing
one detailed XPRS individual:

- display IID: `DEMO_HG00436`;
- public source IID: `HG00436` from the 1000 Genomes Project;
- disease model: breast cancer; and
- reference population: 503 processed East Asian PRS values, with the other
  sample labels replaced by `BACKGROUND_####`.

The relabeling makes the repository's demonstration role explicit. It is not a
claim that the public source sample has been anonymized. The detailed gene and
region contributions are included only for the selected demo individual.

Copying `.env.example` configures a fresh clone to use this bundle.

## Complete processed demonstration dataset

The larger optional artifact is the **full processed 503-sample XPRS
demonstration dataset**, not the full 1000 Genomes Project. It contains the
derived inputs needed by this portal:

```text
data/all_individuals_gene_importance.csv
data/ot_breast_carcinoma_gene_associations.csv
data/plot_cache/annotated_info.parquet
data/plot_cache/prs_info.parquet
data/plot_cache/full_prs.parquet
```

For the initial public release, this artifact is available by contacting the
repository owner through GitHub. Access and redistribution remain subject to
the terms of the upstream 1000 Genomes, PGS Catalog, association-data, and Open
Targets sources. The `source_files` section of `data/demo/manifest.json`
provides SHA-256 checksums and byte sizes for validating the full files supplied
by the author.

After placing the complete files at the paths above, remove or override the
three demo path settings from `.env`:

```dotenv
GENE_IMPORTANCE_CSV=data/all_individuals_gene_importance.csv
OT_MERGED_CSV=data/ot_breast_carcinoma_gene_associations.csv
PLOT_DATA_CACHE_DIR=data/plot_cache
```

Verify the received files against the published manifest before starting the
portal:

```bash
python scripts/verify_full_data.py
```

## Future hosted distribution

Once the upstream reuse review is complete, the full processed artifact may be
published through GitHub Releases, Git LFS, or an institutional data archive.
A versioned release/archive is preferred because it keeps ordinary source-code
clones small and can provide one stable checksum and citation for the complete
bundle. Git LFS remains technically possible, but it should not be enabled
until the public redistribution decision and expected bandwidth are settled.
