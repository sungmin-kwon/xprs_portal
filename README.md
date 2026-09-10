# XPRS Portal

XPRS Portal is a FastAPI application for exploring individual gene contributions
to a polygenic risk score (PRS). It combines cohort-level visualizations,
gene-level contribution rankings, Semantic Scholar literature, Open Targets
associations, and an OpenRouter-powered explanatory chatbot.

The software is distributed under GPL-3.0 in keeping with the upstream XPRS
project. See `NOTICE.md` for attribution and third-party material notices.

The current public cohort is derived from the 1000 Genomes Project. The cohort
catalog also includes a private KFDA multi-disease cohort placeholder, but KFDA
data are not bundled or enabled.

A fresh clone runs against the bundled `DEMO_HG00436` profile. The complete
processed 503-sample XPRS dataset is distributed separately; see
[`DATA_ACCESS.md`](DATA_ACCESS.md).

## Current disease support

The interface presents the planned KFDA disease order:

1. Breast Cancer
2. Type 2 Diabetes
3. Gastric Cancer
4. Colorectal Cancer
5. Uterine Cancer
6. Thyroid Cancer
7. Prostate Cancer
8. Pancreatic Cancer

Only breast cancer currently has XPRS model data and is selectable. Literature
retrieval can still answer explicit questions about other diseases when papers
for the selected genes are available.

## Stack

- FastAPI and Pydantic backend
- Vanilla HTML, CSS, JavaScript, and Plotly frontend
- OpenRouter for generation and GPT-5 mini reference extraction
- Semantic Scholar Graph API for literature discovery
- ChromaDB dense retrieval with BGE-M3 embeddings
- MedCPT cross-encoder reranking
- Pandas/Parquet plot-data cache
- ReportLab PDF reports

The `openai` Python package is used only as an OpenAI-compatible protocol client
for OpenRouter and local vLLM servers. Direct OpenAI and DashScope/Qwen provider
credentials are not supported or required by the current setup.

## Literature retrieval flow

For each gene, the portal maintains separate Chroma metadata pools for general
literature and phenotype-specific literature. A request follows this sequence:

1. Reuse pre-indexed general and breast-cancer pools when the gene appears in
   the frequent-gene sweep; less-frequent genes retain the same on-demand path.
2. Analyze the question as `primary_disease`, `other_disease`, or
   `disease_neutral`.
3. Retrieve a fixed union of dense candidates from relevant phenotype and
   general pools.
4. For an explicitly named non-breast disease, fetch and index a disease-specific
   Semantic Scholar pool on demand if it is not already present.
5. Rerank the candidate union with `ncbi/MedCPT-Cross-Encoder`.
6. Apply a small metadata adjustment:
   - direct requested-disease evidence receives a soft boost;
   - general mechanistic evidence remains available as fallback;
   - other-disease evidence is retained rather than discarded;
   - neutral questions modestly prefer general evidence, with breast cancer used
     only as a tie-breaking context.
7. Return the highest-ranked papers with `disease_match`, `source_pool`, raw
   reranker score, and target-phenotype metadata.

This is not a hard disease quota. A substantially stronger paper from another
disease can still outrank a weak breast-cancer paper. Correction, erratum,
retraction, and expression-of-concern notices are excluded during indexing.

## Repository layout

```text
agents/                 Retrieval, conversation, evidence, and explanation agents
routes/                 FastAPI route modules
static/                 Landing page, dashboard, CSS/JS, and disease-scoped plots
data/                   Public-data manifest/provenance; runtime data is external
r/                      Reproducible legacy R inputs/scripts for plot-data generation
ref/                    Curated XPRS/PRS methodology notes
benchmarks/             Retrieval questions, scripts, and lightweight reports
scripts/                Maintenance and benchmark utilities
tests/                  Focused retrieval-policy and ingestion tests
preindexing.py          Frequency ranking, checkpointing, and pool indexing
server.py               FastAPI entry point
runtime_agents.py       Shared agent/model construction
config.py               Environment and path configuration
```

Runtime directories (`logs/`, `cache_s2/`, and `chroma/`), local environments,
secrets, source-paper copies, large cohort artifacts, generated plots, and
generated benchmark corpora are excluded through `.gitignore`.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --extra-index-url https://download.pytorch.org/whl/cpu \
  -r requirements.lock.txt
cp .env.example .env
```

Populate `OPENROUTER_API_KEY` and, optionally, `S2_API_KEY`. Semantic Scholar can
fall back to its slower public endpoint when its key is absent or rejected.

The repository's `.env.example` selects the bundled one-individual demo data.
See `DATA_ACCESS.md` for the complete processed-data profile. Maintainers with
the reviewed `r/data.RDS` source can rebuild the full Python plot cache with:

```bash
python build_parquet.py
```

Run locally:

```bash
uvicorn server:app --host 127.0.0.1 --port 9009
```

The first retrieval initializes BGE-M3 and MedCPT. Hugging Face model weights
are downloaded to the user cache when not already available.

## Frequent-gene pre-indexing

The pre-indexing script builds a reproducible frequency manifest by counting
each gene's appearances in every available individual's 10 strongest
risk-increasing and 10 strongest risk-lowering contributions. Both directions
receive equal weight. Placeholder identifiers such as `NA_4` are retained in
the local audit manifest but excluded from external queries.

The default hybrid policy pre-indexes the 200 most frequent queryable genes. In
the current 503-individual cohort, these cover 43.6% of all 10,060 top/bottom
slots and require at most 400 Semantic Scholar queries: one general and one
breast-cancer query per gene. Everything outside the cutoff is indexed on
demand. Regenerate the manifest and preview the selection without network use:

```bash
python scripts/preindex_frequent_genes.py
```

For the actual sweep, stop the portal first so the maintenance process is the
only writer to embedded Chroma, then run:

```bash
python scripts/preindex_frequent_genes.py --run
```

When `--run` is present, the script uses the project's `.venv/bin/python`
(or the legacy `.xprs_portal/bin/python` environment, when present), so invoking
it from the base Conda environment still uses the portal's installed
dependencies. It reports a clear setup error if neither environment exists.

The demo configuration writes its frequency manifest under the ignored
`cache_s2/` runtime directory. The existing full-cohort manifest remains a
local, ignored derivative and is not included in the public repository.

The checkpoint at `cache_s2/preindex_state.json` is written atomically after
each gene. Re-running the same command resumes completed work, retries failures,
and reconstructs missing Chroma pools from successful JSON caches. Use
`--max-genes`, `--min-occurrences`, `--sweep-n`, and `--query-delay` to tune the
policy; `--request-timeout` and `--max-attempts` tune pre-index network failure
handling. `--max-genes 0` selects every queryable gene above the occurrence
threshold. An exclusive process lock prevents the maintenance sweep and web
server from writing embedded Chroma at the same time; the port check provides
an earlier human-readable warning when both processes share a network
namespace.

Semantic Scholar requests are spaced by at least two seconds with a small
randomized jitter. The first HTTP 429 opens the circuit immediately without
retrying that query. The checkpoint records `Retry-After` when supplied and an
escalating persistent cooldown (5, 10, 20, then up to 30 minutes). Starting
the script before `cooldown_until` exits with temporary-failure code 75 without
loading models or making an API request. After expiry, the first missing
literature query itself becomes the half-open probe, avoiding a separate
health-check call. Any successful API query resets the consecutive-429
escalation, including a successful general pool followed by a failed phenotype
pool. Pre-index searches use a 45-second read timeout and never retry a read
timeout because the server may still be processing it. Connection failures and
HTTP 5xx responses receive at most two attempts; exhausted transient failures
retain a five-minute cooldown. HTTP 200 with zero eligible documents remains a
valid completed pool, while non-transient errors such as HTTP 400 are recorded
against that gene without treating the entire API as unavailable.

## Read-only literature index browser

An unlinked administration page at `/admin/documents` lists the documents
currently stored in ChromaDB by gene. It supports general-query,
phenotype-query, and Open Targets pool filters; a dynamic query-phenotype
selector; title/abstract search; citation sorting; and expandable stored text.
Pool labels describe retrieval provenance, while extracted phenotype chips
describe the contents of each title and abstract. The page and its API never
return vector embeddings and do not provide any database mutation operations.

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

The survey icon is shown in the primary-page sidebars only while
`XPRS_EVALUATION_TOKEN` is configured. It remains hidden in the default public
configuration, where the evaluation route also returns 404.

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
- `S2_API_KEY`
- `S2_API_KEY_MIN_INTERVAL_SECONDS`, `S2_PUBLIC_MIN_INTERVAL_SECONDS`
- `RERANKER_ENABLED`, `RERANKER_MODEL`, `RERANKER_CANDIDATE_K`
- `RERANKER_BATCH_SIZE`, `RERANKER_MAX_LENGTH`
- `SESSION_LOGGING_ENABLED`
- `EPHEMERAL_SESSION_LIMIT`
- `XPRS_ADMIN_TOKEN` for the unlinked Chroma document browser
- `XPRS_EVALUATION_TOKEN`, `EVALUATION_RESPONSES_DIR`, and
  `XPRS_COOKIE_SECURE` for the internal pilot survey
- optional path overrides such as `DATA_DIR`, `CHROMA_DIR`, `S2_CACHE_DIR`,
  `STATIC_DIR`, and `REF_DIR`

## Tests

```bash
python -m unittest discover -s tests -v
```

The focused suite covers disease-intent resolution, Korean disease aliases,
unknown named phenotypes, soft primary-disease prioritization, explicit
other-disease override, reranker ordering, ingestion hygiene, equal weighting
of risk-increasing/risk-lowering frequency, checkpoint persistence, and
idempotent pre-indexing.

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
- `GET /api/tasks/{task_id}/events` — progress stream
- `GET /api/health/semanticscholar` — Semantic Scholar status/probe
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
