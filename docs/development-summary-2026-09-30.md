# Development summary — 2026-09-30

This document summarizes the K-PREDICT multi-disease integration and related
repository work completed on 2026-09-30. It is intentionally safe to keep in
the public source repository: it contains no private storage paths, source or
pseudonymous participant IDs, restricted keys, or individual variant records.

## Scope and product decisions

- The private cohort is labeled **K-PREDICT**, reflecting the KFDA project from
  which the handoff originated.
- K-PREDICT remains a controlled, authenticated cohort and is not included in
  the public repository or a GitHub release.
- The portal supports the eight planned cancer/metabolic phenotypes plus
  coronary artery disease and myocardial infarction, for ten K-PREDICT disease
  models in total.
- Survival analysis was removed from scope. It depends on long-term follow-up
  data that are generally unavailable and is not part of the current portal.
- Rare-variant findings are intentionally presented as a scrollable list for
  this phase. A chart or survival-style visualization is not required.

## Private-data audit and import pipeline

The repository now contains a reproducible, read-only onboarding workflow for
the original RDS disease models and rare-variant TSV handoff:

- `scripts/audit_kfda_handoff.py` checks the source structure, disease
  crosswalk, cohort consistency, percentile scale, sex-specific applicability,
  rare-finding membership, and other required invariants without modifying the
  source data.
- `scripts/import_kpredict_data.py` creates a versioned private release outside
  the repository.
- `scripts/validate_kpredict_import.py` independently checks the derived
  release's checksums, file permissions, pseudonyms, matrix dimensions,
  applicability totals, and rare-finding indexes.
- `docs/private-cohort-onboarding.md` documents the data contract and operating
  procedure without exposing handoff-specific paths or records.

The importer applies the following controls:

- Source IIDs are replaced by stable HMAC-derived `KP-…` pseudonyms.
- The source-to-pseudonym map and HMAC key are confined to a restricted
  directory that is never served by the application.
- Release directories and files use restrictive permissions.
- The complete contribution matrices are stored as column-major float32 files
  for efficient, one-individual reads.
- Import-time precision checks confirm that float32 conversion preserves the
  top and bottom gene rankings sampled from each matrix.
- Rare findings are stored in a compressed private table, with a separate
  per-individual lookup index.
- Private outputs are rejected if the requested destination is inside the Git
  repository.

The imported private release passed the independent validator.

## K-PREDICT application integration

### Cohort and access control

- The landing page can switch between **1000 Genomes (public)** and
  **K-PREDICT (private)**.
- K-PREDICT availability is controlled by server-side configuration and an
  access token. Unauthorized requests do not disclose whether the private data
  are configured.
- The access token is exchanged for an HTTP-only cookie; it is not placed in
  ordinary query parameters or server access logs.
- Private-cohort authorization is rechecked for individuals, plots, summaries,
  chat, task streams, session access, and report downloads.

### Multi-disease data

The runtime now reads each disease independently from the private release. The
K-PREDICT implementation uses:

- per-individual PRS, standardized risk, percentile, and applicability data;
- disease-specific gene metadata and full gene-contribution matrices;
- supplied population means and variances for gene context and ranking;
- sex-specific applicability for breast, uterine, and prostate cancer; and
- panel-linked and other rare-variant findings.

The ten configured disease models are:

1. Breast Cancer
2. Type 2 Diabetes
3. Gastric Cancer
4. Colorectal Cancer
5. Uterine Cancer
6. Thyroid Cancer
7. Prostate Cancer
8. Pancreatic Cancer
9. Coronary Artery Disease
10. Myocardial Infarction

Availability is evaluated by `(cohort, disease)`. Enabling a K-PREDICT disease
does not enable it for the public 1000 Genomes demonstration.

### Visual and interactive use

For an authorized K-PREDICT user, the portal now provides:

- the complete pseudonymous individual selector;
- a ten-disease risk overview with non-applicable disease cards disabled;
- an individual PRS density plot calculated against the applicable K-PREDICT
  reference population;
- a gene-contribution Manhattan plot generated directly from the selected
  disease matrix;
- top contributing genes for summary generation; and
- a scrollable rare-variant list separated into active-disease and other
  findings, with alert and carrier counts.

The rare-variant release preserves the full imported record. The current UI
shows a deliberately curated clinical subset, including gene, variant,
genotype, consequence, clinical significance, confidence tier, inheritance
classification, and ClinVar condition. Rare variants are not included in LLM
prompts.

## Disease-independent explanation runtime

The explanation path was separated from the legacy 1000 Genomes breast-cancer
matrix:

- K-PREDICT uses a disease- and release-scoped gene-importance agent that reads
  only the selected individual's contribution column.
- Each explanation agent receives the active disease's name, retrieval
  phenotype, risk distribution, and gene matrix.
- Breast-cancer-specific Open Targets data are not presented as evidence for
  other diseases.
- Summary and chat sessions for K-PREDICT remain in process memory rather than
  being written to persistent session logs.
- Reports and follow-up questions retain the active cohort and disease context.

### Hosted-model privacy controls

All hosted generation and metadata extraction now use OpenRouter through its
OpenAI-compatible protocol. Direct OpenAI and separate Qwen-provider credential
paths are no longer required.

K-PREDICT requests require Zero Data Retention and deny provider data
collection. Prompts are restricted to the active disease, selected gene
symbols, rank-only wording, and public literature. The common client boundary
also removes K-PREDICT IDs, rsIDs, HGVS strings, and genotypes if they appear
unexpectedly. Exact PRS values, percentiles, gene contributions, complete
vectors, demographics, and rare-variant records are excluded from hosted-model
prompts.

These technical controls complement, but do not replace, institutional and
data-owner approval for external processing.

## Semantic Scholar and RAG revisions

The literature retrieval pipeline is shared by the public and private cohorts.
It was revised to reduce expensive first-use requests and make enrichment
incremental:

- Semantic Scholar relevance search uses checkpointed pages of ten results.
- A cold interactive request retrieves the initial general and active-disease
  pages.
- If fewer than five unique eligible documents survive filtering, at most one
  additional page is retrieved synchronously.
- Incomplete pools are queued for a single background enrichment worker that
  yields to interactive retrieval.
- Background targets are 30 eligible general papers, 20 primary-disease
  papers, and 15 papers for another explicitly requested disease.
- Enrichment stops at the eligible target, source exhaustion, 50 raw results,
  or two consecutive pages with no eligible additions.
- Cache offsets and enrichment status are written atomically so interrupted
  work can resume without repeating completed pages.
- Chroma embedding and upsert operations are serialized between interactive
  and background work.
- The former public-cohort frequency sweep was subsequently removed; the
  current portal indexes observed genes on demand across literature providers.

Document eligibility currently requires a Semantic Scholar paper ID, a usable
abstract, an explicit gene mention, and at least one citation. Correction,
erratum, retraction, and expression-of-concern notices are excluded.

The number of indexed documents is independent of the LLM selected for answer
generation. Chroma dense retrieval and MedCPT reranking determine the context
presented to GPT, Claude, Qwen, or Gemma.

## Repository sanitization and documentation

The repository was prepared for a public/private split in which code is public
and controlled cohort data remain external:

- Private source files, derived releases, caches, vector stores, session logs,
  evaluation responses, and local environments are excluded through `.gitignore`.
  Plot payloads are now generated in memory rather than written beneath
  `static/`.
- Legacy R scripts that depended on unavailable local source data were removed;
  the remaining `r/README.md` explains the legacy rebuild boundary.
- `README.md`, `DATA_ACCESS.md`, `SECURITY.md`, `NOTICE.md`, and the data
  documentation were updated for K-PREDICT, ZDR, and the external-data model.
- `scripts/check_public_repo.py` checks tracked and unignored files for common
  credential formats, private cohort filenames, internal storage paths, and
  evaluation artifacts without printing secret values.
- The public repository hygiene check currently passes.

## Verification performed

The following checks were completed after integration:

- independent validation of the complete private release;
- authenticated live checks for cohort availability and individual loading;
- density, Manhattan, multi-disease overview, and rare-finding API smoke tests;
- a two-gene K-PREDICT summary preview;
- an end-to-end hosted-model summary with indexed literature and a report-ready
  result;
- FastAPI OpenAPI generation;
- the public-repository hygiene check; and
- the complete automated test suite, with 119 tests passing.

The live portal was restarted in the `xprs` tmux session and is serving the
integrated build on port 9009.

## Current limitations and follow-up work

The data integration and guided demonstration path are functional. Remaining
work is operational or incremental rather than a missing-data blocker:

1. **Persist private deployment configuration.** K-PREDICT is enabled in the
   current service process. A controlled environment file or service launcher
   should preserve the enable flag and private data root across independent
   restarts without committing either setting.
2. **Strengthen the shared 429 circuit breaker.** Adaptive pagination reduces
   request size, but live validation still observed Semantic Scholar throttling
   during background enrichment. One 429 should pause the entire background
   queue before another job is attempted.
3. **Pre-index selected multi-disease demonstration genes.** The disease models
   are complete, but literature coverage is populated on demand for
   all ten phenotypes. A guided breast-cancer summary can rely on existing
   indexed evidence; arbitrary disease/gene combinations may still require a
   live Semantic Scholar request.
4. **Review generation latency.** The end-to-end summary path succeeded, but
   model generation can dominate the wait even when data and literature are
   already local. Model/provider timing should be considered when choosing a
   live-demo model.
5. **Expand rare-variant details only if needed.** The source fields remain in
   the private release, while the current list intentionally shows a curated
   subset. Additional frequency, quality-control, or enrichment fields can be
   added later without changing the import format.

Survival analysis and a rare-variant chart are not pending items: both are
deliberately outside the current scope.
