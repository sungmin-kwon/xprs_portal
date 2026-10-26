# Private multi-disease cohort onboarding

This document defines the code-facing contract for a controlled K-PREDICT
deployment. It intentionally contains no source paths, participant identifiers,
or handoff-specific aggregate counts. Private source data and generated audit
manifests remain outside the public repository.

## Read-only handoff audit

Run the structural audit before converting any data:

```bash
python scripts/audit_kfda_handoff.py \
  --rds-dir /PRIVATE/RDS/DIRECTORY \
  --rare-tsv /PRIVATE/RARE_FINDINGS.tsv \
  --handoff-id REVIEWED-NONIDENTIFYING-LABEL \
  --output /PRIVATE/AUDIT/manifest.json
```

The output path must be outside the repository. The manifest is aggregate-only,
records neither source paths nor participant IDs, and is written with mode
`0600`. Add `--hash-files` when producing a frozen handoff manifest; this reads
all source files to calculate SHA-256 checksums.

## Disease crosswalk

| Source disease ID | Portal disease slug | Current UI status |
|---|---|---|
| `breast_cancer` | `breast_cancer` | available when imported |
| `diabetes` | `type2_diabetes` | available when imported |
| `gastric_cancer` | `gastric_cancer` | available when imported |
| `colorectal_cancer` | `colorectal_cancer` | available when imported |
| `uterine_cancer` | `uterine_cancer` | available when imported |
| `thyroid_cancer` | `thyroid_cancer` | available when imported |
| `prostate_cancer` | `prostate_cancer` | available when imported |
| `pancreatic_cancer` | `pancreatic_cancer` | available when imported |
| `coronary_artery_disease` | `coronary_artery_disease` | available when imported |
| `myocardial_infarction` | `myocardial_infarction` | available when imported |

Availability must be keyed by `(cohort, disease)`. Enabling a disease for K-PREDICT
must not enable that disease for the public 1000 Genomes demonstration.

## RDS contract

Each disease object must provide:

- `disease_id` and `disease_label`;
- `PRS_info`, with one column per cohort individual;
- `annotated_info`, row-aligned with `PRS_info` and containing `symbol`, genomic
  coordinates, `variance`, and `within_region_rank_by_variance`;
- `full_prs`, containing unique `IID` and raw `PRS` columns;
- `z`, `pct`, `ref_mean`, and `ref_sd`.

The audit verifies that `z = (PRS - ref_mean) / ref_sd`, that all disease files
share one cohort IID set, and that every rare-finding IID exists in every RDS.
The supplied `pct` values use the **0–100** scale. Sex-inapplicable phenotypes
are represented by missing `z` and `pct` values and must remain unavailable in
the UI rather than being displayed as zero risk.

Raw PRS values are disease-specific and must not be compared across diseases or
cohorts. Gene contributions use a different scale from raw PRS, cannot be
summed to reconstruct PRS, and require the supplied variance/ranking metadata
for cross-gene ordering.

## Rare-finding contract

One TSV row represents an `(IID, variant, gene, disease)` finding. The importer
must preserve the supplied `moi_call` and `moi_why` fields:

- `alert`: a finding designated for prominent review;
- `carrier`: a recessive heterozygous carrier finding, displayed separately and
  not styled as an alert.

`track=panel` belongs with its supplied `xprs_disease`. The dashboard shows the
active disease first and retains panel findings for other diseases in separate,
collapsible disease groups. `track=other` has no validated XPRS disease assignment
and belongs in a distinct “Other findings” view; it must not be discarded or
assigned from free-text ClinVar disease names. Source disease IDs are normalized
to portal slugs during import (`diabetes` becomes `type2_diabetes`), and the
runtime applies the same normalization for releases imported before this rule.

## Importer output boundary

The next-stage importer should produce a versioned private data root containing:

- individual risk data (`PRS`, `z`, 0–100 percentile, applicability);
- gene metadata and variance-aware representative/ranking fields;
- a contribution store that can project one individual without loading an
  entire disease matrix;
- precomputed top increasing and lowering contributions; and
- an indexed rare-finding store.

No derivative may be written under `static/`, committed to Git, placed in a
GitHub release, or named with a source IID. K-PREDICT endpoints must be authenticated
server-side before this data root is connected to the web application.

## Versioned import

After a handoff passes the read-only audit, create a private release with:

```bash
python scripts/import_kpredict_data.py \
  --rds-dir /PRIVATE/RDS/DIRECTORY \
  --rare-tsv /PRIVATE/RARE_FINDINGS.tsv \
  --output-root /PRIVATE/XPRS_DATA \
  --release YYYY-MM-DD \
  --handoff-id REVIEWED-NONIDENTIFYING-LABEL \
  --audit-manifest /PRIVATE/AUDIT/manifest.json
```

The importer refuses repository-local output and an existing release path. It
uses a mode-0700 staging directory and publishes the completed release with one
atomic rename. Source IIDs are replaced with stable HMAC-derived `KP-…`
pseudonyms. The source-to-pseudonym map and HMAC key are stored under the
release's mode-0700 `_restricted/` directory; application endpoints must never
return either file.

Each disease directory contains:

- `individual_risk.parquet`, in contribution-matrix column order;
- `genes.parquet`, in contribution-matrix row order;
- `contributions.f32`, a little-endian, column-major float32 matrix; and
- `matrix.json`, which records the shape and index tables.

The importer samples 25 matrix columns and rejects conversion when float32
rounding changes a top-10 or bottom-10 ordering or exceeds the configured
absolute-error tolerance. Rare findings are written to `rare_findings.parquet`
with pseudonymous finding and individual IDs, plus an aggregate
`rare_finding_index.parquet` for efficient individual lookup.

Validate the published release independently:

```bash
python scripts/validate_kpredict_import.py \
  --release-dir /PRIVATE/XPRS_DATA/kpredict/YYYY-MM-DD
```

This recalculates all derived checksums and validates file permissions,
pseudonym sets, matrix dimensions, applicability counts, and rare-finding index
totals without printing participant identifiers.

## Hosted explanation privacy policy

K-PREDICT summary and chat routes require the same server-side authorization as
the cohort data endpoints. The explanation runtime is instantiated per
`(model, cohort, disease, release)` and uses that disease's contribution matrix,
percentile distribution, label, and retrieval phenotype. It does not fall back
to the public 1000 Genomes breast-cancer matrix.

All OpenRouter calls require provider-side Zero Data Retention and deny provider
data collection. Prompts are limited to the active disease, selected gene symbols,
public papers, and rank-only wording. They exclude pseudonymous IIDs, demographic
fields, exact PRS/percentiles, exact gene contributions, full vectors, and all
rare-variant details. A final sanitizer removes any K-PREDICT IID, rsID, HGVS
string, or genotype that reaches the common client boundary. Private sessions
are kept in process memory rather than persisted to disk. Task streams, session
exports, and report downloads re-check K-PREDICT authorization.

These controls reduce disclosure but do not make pseudonymized genetic data
anonymous. Deployment still requires institutional/data-owner approval and a
review of external processors and retention terms.
