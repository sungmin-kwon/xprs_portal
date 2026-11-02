# XPRS Portal

XPRS Portal is a FastAPI application for exploring individual gene contributions
to a polygenic risk score (PRS). It combines cohort-level visualizations,
gene-level contribution rankings, biomedical literature, Open Targets
associations, and an OpenRouter-powered explanatory chatbot.

The software is distributed under GPL-3.0 in keeping with the upstream XPRS
project. See `NOTICE.md` for attribution and third-party material notices.

The public cohort is derived from the 1000 Genomes Project. The same codebase
can also serve K-PREDICT as an authenticated private deployment from an external
data root. K-PREDICT data are never bundled or committed to this repository.

A fresh clone runs against the bundled `DEMO_HG00436` profile. The complete
processed 503-sample XPRS dataset is distributed separately; see
[`DATA_ACCESS.md`](DATA_ACCESS.md).

## Disease support

The interface presents this K-PREDICT disease order:

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

An authenticated K-PREDICT deployment enables whichever validated disease
artifacts are present in its configured private release. The public 1000 Genomes
demo remains breast-cancer-only. Cohort and disease availability are evaluated
independently, so enabling a K-PREDICT disease never exposes it in the public
cohort.

Literature retrieval can still answer explicit questions about other diseases
when papers for the selected genes are available.

## Stack

- FastAPI and Pydantic backend
- Vanilla HTML, CSS, JavaScript, and Plotly frontend
- OpenRouter for generation and GPT-5 mini reference extraction
- Europe PMC REST API with Semantic Scholar as an emergency literature fallback
- ChromaDB dense retrieval with BGE-M3 embeddings
- MedCPT cross-encoder reranking
- Pandas/Parquet plot-data cache
- ReportLab PDF reports

The `openai` Python package is used only as an OpenAI-compatible protocol client
for OpenRouter and local vLLM servers. Direct OpenAI and DashScope/Qwen provider
credentials are not supported or required by the current setup.

## Literature retrieval flow

For each gene, the portal maintains separate Chroma metadata pools for general
literature and phenotype-specific literature. Provider-specific query responses
are cached separately, while eligible records share one source-tagged Chroma
collection. A request follows this sequence:

1. Reuse any indexed general and primary-disease pools. For a cold gene, query
   the public Europe PMC REST API and index up to 25 source results.
2. Skip the second, disease-specific Europe PMC request when the general pool
   already contains at least five eligible papers, including at least two that
   explicitly match the active disease. Otherwise, query the disease-specific
   pool to restore relevant evidence.
3. If Europe PMC and the local index still provide no usable literature, let
   answer generation continue and enqueue one 10-result Semantic Scholar page
   as an emergency background fallback. The chatbot never waits for this
   request or paginates it automatically.
4. An administrator can explicitly continue an incomplete Semantic Scholar
   cache. Each action advances at most one page through the shared worker,
   preserving the cached offset and yielding to interactive retrieval.
5. Analyze the question as `primary_disease`, `other_disease`, or
   `disease_neutral`.
6. Retrieve a fixed union of dense candidates from relevant phenotype and
   general pools.
7. For an explicitly named non-primary disease, populate a disease-specific
   Europe PMC pool on demand and enqueue one Semantic Scholar fallback page
   only when no usable local literature is available.
8. Rerank the candidate union with `ncbi/MedCPT-Cross-Encoder`.
9. Apply a small metadata adjustment:
   - direct requested-disease evidence receives a soft boost;
   - general mechanistic evidence remains available as fallback;
   - other-disease evidence is retained rather than discarded;
   - neutral questions modestly prefer general evidence, with the active
     primary disease used only as a tie-breaking context.
10. Return the highest-ranked papers with `disease_match`, `source_pool`, raw
   reranker score, and target-phenotype metadata.

Semantic Scholar fallback and continuation work runs outside the interactive
answer path and is limited to one page per queued action. Repeated explicit
admin continuations can still work toward the configured coverage targets, but
the portal no longer launches an unattended multi-page sweep. Canonical
phenotype queries can fall through to up to two
configured phenotype aliases; ambiguous short symbols can also fall through
to broader symbol queries. Each strategy is capped at 50 raw results, and a
low-yield strategy gives way to the next strategy after two consecutive pages
that add no eligible documents. Results are deduplicated across strategies.
Eligibility requires a
paper ID, abstract, validated gene identity, and at least one citation;
correction, erratum, retraction, and expression-of-concern notices are excluded.
Short symbols that can also be ordinary acronyms are searched with gene-sense
context and require either an official name/alias match or semantic identity
validation, so broader fallback queries cannot make acronym collisions citable.
A versioned final citation gate prevents records produced by older
lexical-only rules from being used while their pool is rebuilt. These corpus
limits do not depend on the answer-generation model.

Disease-aware ranking is not a hard quota. A substantially stronger paper from
another disease can still outrank a weak primary-disease paper.

Reference links prefer PubMed Central when a PMCID is available and PubMed when
only a PMID is available. Semantic Scholar remains the link destination for
fallback records without an NCBI identifier.

## Repository layout

```text
agents/                 Retrieval, conversation, evidence, and explanation agents
routes/                 FastAPI route modules
static/                 Landing page, dashboard, CSS/JS, and vendored browser assets
data/                   Public-data manifest/provenance; runtime data is external
docs/                   Data-contract and deployment documentation
r/                      Documentation for the ignored legacy RDS input location
ref/                    Curated XPRS/PRS methodology notes
benchmarks/             Retrieval questions, scripts, and lightweight reports
scripts/                Maintenance and benchmark utilities
tests/                  Focused retrieval-policy and ingestion tests
server.py               FastAPI entry point
runtime_agents.py       Shared agent/model construction
config.py               Environment and path configuration
```

Runtime directories (`logs/`, provider caches, and `chroma/`), local environments,
secrets, source-paper copies, large cohort artifacts, and generated benchmark
corpora are excluded through `.gitignore`. Plot payloads are generated in memory
and are not stored under `static/`.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Populate `OPENROUTER_API_KEY` and, optionally, `S2_API_KEY`. Semantic Scholar can
fall back to its slower public endpoint when its key is absent or rejected.
Every OpenRouter request is routed with Zero Data Retention required and provider
data collection denied. The application refuses to call OpenRouter when that
policy is disabled.

The repository's `.env.example` selects the bundled one-individual demo data.
See `DATA_ACCESS.md` for the complete processed-data profile. Maintainers with
the reviewed `r/data.RDS` source can rebuild the full Python plot cache with:

```bash
python build_parquet.py
```

This conversion utility is limited to the legacy public breast-cancer profile.
It is not the importer for private multi-disease data.

The private cohort contract and audit workflow are documented in
[`docs/private-cohort-onboarding.md`](docs/private-cohort-onboarding.md).
The corresponding importer and independent release validator are
`scripts/import_kpredict_data.py` and `scripts/validate_kpredict_import.py`.

Run locally:

```bash
uvicorn server:app --host 127.0.0.1 --port 9009
```

The first retrieval initializes BGE-M3 and MedCPT. Hugging Face model weights
are downloaded to the user cache when not already available.

## Read-only retrieval administration

The unlinked `/admin/documents` page combines retrieval-coverage monitoring
with the earlier gene-by-gene ChromaDB document browser. Its coverage table is
cohort-neutral: it reports every gene observed in a provider cache or ChromaDB,
along with cached query responses, indexed documents, pagination
completion, manual continuation, and active cooldowns. It does not divide
genes into the legacy public-cohort plan and an "outside plan" group.

For missing or interrupted pools, an administrator can issue one manual
literature query from the coverage table. This action uses the same
serialized request lock, rate-limit cooldown, cache, document eligibility
rules, Chroma upsert path, and serialized continuation queue as chatbot-driven
retrieval. Cached papers are processed before any upstream request. A first
manual action can create one Semantic Scholar fallback cache; each subsequent
continuation advances that cache by at most one page.

The Semantic Scholar status card also provides an explicit API-key check. It
sends one keyed, one-result request only when clicked, reports authentication
failure separately from rate limiting or network failure, and never exposes the
key. Active probes on the general health endpoint require the same admin token;
ordinary health reads are non-probing.

The General and phenotype-specific pools describe query provenance rather than
mutually exclusive subject categories. A gene-only General search may return a
breast-cancer paper that is also returned by a `gene + breast cancer` search.
Both provenance records can be retained in ChromaDB, while retrieval candidate
assembly deduplicates matching Semantic Scholar paper IDs before reranking.

The Documents view retains the general-query, phenotype-query, and Open
Targets filters; dynamic query-phenotype selector; title/abstract search;
citation sorting; and expandable stored text. The page and its APIs never
return vector embeddings and do not provide database mutation operations.

Set `XPRS_ADMIN_TOKEN` and open the page once as
`/admin/documents#token=VALUE`. URL fragments are not transmitted in HTTP
requests or access logs. The browser exchanges the fragment for an HTTP-only,
same-site cookie and removes it from the visible URL. When no token is
configured, the page and its APIs return 404.

## Internal pilot evaluation

The optional `/evaluation` page implements the 30-item `pilot-v1` usability
instrument: participant consent and background, task completion, fourteen
portal-rating items, three comprehension checks, and four open-ended prompts.
The optional System Usability Scale is not included in this pilot version.

Set a separate `XPRS_EVALUATION_TOKEN`, restart the server, and give an
evaluator a link of the following form:

```text
https://PORTAL_HOST/evaluation#token=VALUE
```

The fragment after `#` is not sent in the initial HTTP request or written to
the server access log. After access is validated, the page places the token in
an HTTP-only, same-site cookie and removes it from the visible URL. Set
`XPRS_COOKIE_SECURE=true` when the portal is served through HTTPS. Responses
are written as mode-0600 JSON files under the ignored
`evaluation_responses/` directory. Response records contain the anonymous
participant/session codes supplied in the form, but deliberately omit IP
address and browser metadata.

The overview and dashboard retain a disabled survey icon as a reminder that the
study UI is deferred. The methodology page exposes its survey link only when
`XPRS_EVALUATION_TOKEN` is configured; otherwise the evaluation route returns
404.

Export the collected records to an analysis-ready CSV, including the
prespecified rating-group means, task indicators, and comprehension scores:

```bash
python scripts/export_evaluation_responses.py
```

Do not collect names, email addresses, health information, or other direct
identifiers. Confirm the consent language, retention period, participant
instructions, and any required IRB/ethics review before beginning a study
intended for publication.

## Environment variables

The complete key-free template is in `.env.example`. The principal settings are:

- `OPENROUTER_API_KEY`, `LLM_MODEL`
- `REFERENCE_EXTRACTION_PROVIDER=openrouter`
- `REFERENCE_EXTRACTION_MODEL=openai/gpt-5-mini`
- `LITERATURE_CACHE_DIR`, `EUROPE_PMC_CACHE_DIR`, `S2_CACHE_DIR`, `S2_API_KEY`
- `S2_API_KEY_MIN_INTERVAL_SECONDS`, `S2_PUBLIC_MIN_INTERVAL_SECONDS`,
  `S2_ENRICHMENT_API_KEY_MIN_INTERVAL_SECONDS`
- `KPREDICT_ENABLED`, `KPREDICT_DATA_ROOT`, `XPRS_KPREDICT_TOKEN`
- `LITERATURE_MINIMUM_INTERACTIVE_ELIGIBLE_DOCUMENTS`
- `RERANKER_ENABLED`, `RERANKER_MODEL`, `RERANKER_CANDIDATE_K`
- `RERANKER_BATCH_SIZE`, `RERANKER_MAX_LENGTH`
- `SESSION_LOGGING_ENABLED`
- `EPHEMERAL_SESSION_LIMIT`
- `XPRS_ADMIN_TOKEN` for the unlinked retrieval administration page
- `XPRS_EVALUATION_TOKEN`, `EVALUATION_RESPONSES_DIR`, and
  `XPRS_COOKIE_SECURE` for the internal pilot survey
- optional path overrides such as `DATA_DIR`, `CHROMA_DIR`,
  `STATIC_DIR`, and `REF_DIR`

## Tests

```bash
python -m unittest discover -s tests -v
```

See [`tests/README.md`](tests/README.md) for the suite organization and test
fixture conventions.

Before committing or publishing, also run the repository hygiene check:

```bash
python scripts/check_public_repo.py
```

Provider cache metadata can be audited without making literature requests:

```bash
python scripts/reconcile_literature_cache.py
```

After reviewing the dry run, add `--write` to atomically reconcile stored
eligibility counts with the current cache-to-Chroma policy.

It checks tracked and unignored files for common credential formats, internal
storage paths, evaluation responses, and private-cohort filenames without
printing any matched secret value.

The focused suite covers disease-intent resolution, Korean disease aliases,
unknown named phenotypes, soft primary-disease prioritization, explicit
other-disease override, reranker ordering, multi-provider ingestion, source
identity, and repository hygiene.

Retrieval comparison reports are retained under `benchmarks/`. Generated
corpora, abstracts, embeddings, Chroma/LanceDB indexes, and blinded-review files
are intentionally excluded from the public repository surface.

## API highlights

- `GET /` — landing page
- `GET /dashboard` — dashboard
- `GET /evaluation` — internal pilot survey; response submission is token-protected
- `GET /api/cohorts` — cohort catalog
- `GET /api/diseases` — ordered disease catalog
- `GET /api/individuals` — available individual IDs
- `POST /api/summary/start` — asynchronous summary generation
- `POST /api/chat/start` — asynchronous follow-up question
- `GET /api/tasks/{task_id}` — recoverable asynchronous task status and result
- `GET /api/tasks/{task_id}/events` — progress stream
- `GET /api/health/semanticscholar` — non-probing Semantic Scholar status
- `GET /api/health/rag` — dense store and reranker configuration status
- `POST /api/report/pdf` — PDF report

The read-only administration routes and survey submission API are intentionally
omitted from this public API list and from the generated OpenAPI schema.

## Public data and GitHub size

`data/all_individuals_gene_importance.csv`, `r/data.RDS`, and the generated
`prs_info.parquet` are each roughly 60–75 MB. They are explicitly ignored so an
ordinary `git add` cannot publish them accidentally. A compact, reproducible
`DEMO_HG00436` profile is tracked directly. The complete processed 503-sample
profile is initially available from the repository author and can later move
to a versioned release artifact after the remaining upstream reuse review.

## Privacy and generated state

Session logs may contain user questions and generated interpretations.
Persistent logging is disabled by default; bounded in-memory sessions preserve
follow-up and report functionality until the process restarts. Enable disk logs
only for a controlled deployment with an appropriate retention policy. Never
publish `.env`, `logs/`, Semantic Scholar caches, or Chroma runtime files.

Private K-PREDICT inputs are a separate controlled-deployment concern.
They must live outside the repository data root, remain behind server-side
authentication, and never be written to public static plot files. Individual
IDs, genotypes, variants, HGVS values, and individual contribution data must
not be sent to Semantic Scholar or an externally hosted language model without
an approved data-governance policy.

## License and attribution

XPRS Portal is licensed under the GNU General Public License version 3. The
software license applies to repository code, not automatically to cohort data,
model weights, publications, or content returned by external APIs. See
`NOTICE.md` and `data/README.md` before redistributing those materials.

## Research-use guardrails

The portal presents research associations and cohort-relative statistical
signals, not diagnoses or individualized medical advice. Generation prompts
forbid diagnostic claims, treatment recommendations, and unsupported numeric
prognoses. A conservative conversation classifier declines clearly personal,
action-seeking medical requests while allowing general biomedical questions.
