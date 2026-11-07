# XPRS Portal administration runbook

This runbook covers a single-process XPRS Portal deployment on a login or
application node. Replace `/path/to/xprs_portal` and `PORTAL_HOST` with the
local deployment values. The runbook deliberately excludes secret values and
private participant data.

## Deployment at a glance

| Item | Current deployment |
|---|---|
| Project directory | `/path/to/xprs_portal` |
| Python environment | `.xprs_portal/` |
| Application | FastAPI/Uvicorn, `server:app` |
| Service port | `9009`, bound to `0.0.0.0` |
| tmux session | `xprs` |
| Local health check | `http://127.0.0.1:9009/healthz` |
| Browser entry point | `http://PORTAL_HOST:9009/` |
| Public cohort | 1000 Genomes demonstration |
| Private cohort | K-PREDICT, protected by server-side access checks |
| LLM gateway | OpenRouter with ZDR required and data collection denied |
| Literature sources | Europe PMC first; Semantic Scholar emergency fallback |
| Vector store | Local ChromaDB with BGE-M3 embeddings and MedCPT reranking |

The service is currently run in tmux, not by systemd. A machine reboot or a
terminated tmux server therefore requires a manual restart.

## Emergency recovery: portal is unreachable

### 1. Check the session, process, and port

```bash
cd /path/to/xprs_portal
tmux ls
ss -ltnp | grep ':9009'
ps -ef | grep '[u]vicorn.*server:app'
```

If `xprs` exists, inspect its latest output:

```bash
tmux capture-pane -p -t xprs:0.0 -S -200
```

Do not start a second portal process while the first is alive. ChromaDB is
protected by a single-process lock, and two application processes must not
write the same store.

### 2. Start a missing service

Use the project environment and bind to all interfaces:

```bash
cd /path/to/xprs_portal
tmux new-session -d -s xprs -c /path/to/xprs_portal \
  'exec ./.xprs_portal/bin/uvicorn server:app --host 0.0.0.0 --port 9009'
```

Startup loads BGE-M3 and the application data before Uvicorn reports that the
application is ready. This can take roughly 30 seconds or longer under load.
Watch startup rather than repeatedly launching it:

```bash
tmux capture-pane -p -t xprs:0.0 -S -200
```

Wait for both messages:

```text
Runtime warmup complete
Application startup complete
```

### 3. Verify the recovered service

```bash
curl -fsS http://127.0.0.1:9009/healthz
curl -sS -o /dev/null -w 'landing HTTP %{http_code}\n' \
  http://127.0.0.1:9009/
curl -sS -o /dev/null -w 'dashboard HTTP %{http_code}\n' \
  http://127.0.0.1:9009/dashboard
```

Expected results are `{"status":"ok"}` and HTTP 200 for both pages. Also
confirm `ss -ltnp | grep ':9009'` shows `0.0.0.0:9009`.

If local checks pass but the public IP is unreachable, the application is
healthy; check the login-node firewall, network route, or institutional access
policy rather than restarting Uvicorn repeatedly.

## Routine tmux operations

Attach to the live console:

```bash
tmux attach -t xprs
```

Detach without stopping the portal by pressing `Ctrl-b`, then `d`.

Read recent output without attaching:

```bash
tmux capture-pane -p -t xprs:0.0 -S -300
```

### Controlled restart

First stop only the named application session:

```bash
tmux send-keys -t xprs:0.0 C-c
```

Confirm that port 9009 is no longer listening. If the stopped tmux session
remains, remove that session only:

```bash
tmux kill-session -t xprs
```

Then use the startup command in the emergency recovery section. Never use a
broad `pkill python`, and never kill unrelated tmux sessions.

## Configuration and secrets

Runtime configuration is read from `.env` during startup. `.env` is ignored by
Git; `.env.example` documents the supported variables and safe public defaults.

Important settings include:

- `OPENROUTER_API_KEY`: the only LLM API credential;
- `S2_API_KEY`: optional Semantic Scholar credential;
- `LITERATURE_CACHE_DIR`: shared root for the Europe PMC and Semantic Scholar
  provider caches;
- `XPRS_ADMIN_TOKEN`: administrator access code;
- `XPRS_KPREDICT_TOKEN`: dedicated private-cohort access code;
- `XPRS_EVALUATION_TOKEN`: enables the internal evaluation page when nonempty;
- `KPREDICT_ENABLED` and `KPREDICT_DATA_ROOT`: enable and locate the private
  release;
- `GENE_IMPORTANCE_CSV`, `OT_MERGED_CSV`, and `PLOT_DATA_CACHE_DIR`: public
  demonstration data paths;
- `XPRS_COOKIE_SECURE`: use `true` only when the browser reaches the portal
  through HTTPS; and
- `SESSION_LOGGING_ENABLED`: keep `false` for the current privacy posture.

After changing `.env`, restart the portal. Existing processes do not reload
environment changes automatically.

Security rules:

1. Never put actual credentials in `.env.example`, documentation, Git commits,
   screenshots, shell history, or chat messages.
2. Never add K-PREDICT files, imported releases, evaluation responses, caches,
   or generated reports to Git/Git LFS/GitHub Releases.
3. Keep `.env` readable only by the account owner:

   ```bash
   chmod 600 /path/to/xprs_portal/.env
   ```

4. Rotate a token immediately if it is disclosed, update `.env`, and restart
   the service.

## Protected browser access

Tokens are supplied in the URL fragment (`#token=...`), exchanged for an
HTTP-only cookie, and then removed from the visible URL. Fragments are not sent
in the initial HTTP request or written to the access log.

### K-PREDICT

Use the dedicated K-PREDICT token rather than distributing the administrator
token:

```text
http://PORTAL_HOST:9009/?cohort=kpredict#token=VALUE
```

The K-PREDICT cookie lasts 12 hours. A browser with an old or missing cookie
may show the private cohort label while reporting that its access code was not
accepted. Reopen the fragment link with the current token. Server endpoints
return HTTP 404 rather than revealing whether private data are configured.

### Retrieval administration

```text
http://PORTAL_HOST:9009/admin/documents#token=VALUE
```

The administrator cookie lasts 8 hours. The page returns 404 when
`XPRS_ADMIN_TOKEN` is unset or the code is invalid. It provides:

- per-gene retrieval coverage and stored-document inspection;
- general and phenotype-specific query-pool status;
- cached-result indexing and explicit retry actions;
- per-source success, failure, and eligibility status;
- exact indexed-document deletion while preserving provider caches; and
- an explicit Semantic Scholar API-key check.

Do not repeatedly click a query action. Check the background queue and active
request shown by the page. Europe PMC is the primary live source. A Semantic
Scholar fallback makes at most one request for 10 raw papers; a successful
response is terminal even if no paper passes the indexing rules. Failed or
rate-limited requests may be retried later. HTTP 429 indicates provider
throttling, not necessarily an invalid key; the key checker distinguishes
authentication failure from rate limiting.

### Internal evaluation page

The evaluation feature is intentionally de-emphasized in the current UI. When
enabled, its access link is:

```text
http://PORTAL_HOST:9009/evaluation#token=VALUE
```

Responses are private runtime data. Export them with:

```bash
cd /path/to/xprs_portal
./.xprs_portal/bin/python scripts/export_evaluation_responses.py \
  --output /PRIVATE/OUTPUT/evaluation-responses.csv
```

## Data profiles

### Public 1000 Genomes demonstration

The repository contains a one-individual demonstration bundle. The optional
complete processed 503-sample demonstration data are described in
`DATA_ACCESS.md`. Validate a supplied complete bundle with:

```bash
./.xprs_portal/bin/python scripts/verify_full_data.py
```

### Private K-PREDICT release

The active private release lives outside the repository. Its source IDs are
replaced by stable `KP-...` pseudonyms, but the data remain sensitive genetic
data and must be handled as private.

Before importing a new handoff, follow
`docs/private-cohort-onboarding.md`. The high-level sequence is:

1. audit the source handoff into an aggregate-only manifest;
2. import into a new versioned release outside the repository;
3. independently validate that release;
4. change `KPREDICT_DATA_ROOT` to the reviewed release; and
5. restart and test the portal.

Core commands are:

```bash
./.xprs_portal/bin/python scripts/audit_kfda_handoff.py \
  --rds-dir /PRIVATE/RDS/DIRECTORY \
  --rare-tsv /PRIVATE/RARE_FINDINGS.tsv \
  --handoff-id REVIEWED-NONIDENTIFYING-LABEL \
  --output /PRIVATE/AUDIT/manifest.json

./.xprs_portal/bin/python scripts/import_kpredict_data.py \
  --rds-dir /PRIVATE/RDS/DIRECTORY \
  --rare-tsv /PRIVATE/RARE_FINDINGS.tsv \
  --output-root /PRIVATE/XPRS_DATA \
  --release YYYY-MM-DD \
  --handoff-id REVIEWED-NONIDENTIFYING-LABEL \
  --audit-manifest /PRIVATE/AUDIT/manifest.json

./.xprs_portal/bin/python scripts/validate_kpredict_import.py \
  --release-dir /PRIVATE/XPRS_DATA/kpredict/YYYY-MM-DD
```

Do not overwrite an existing release. Keep the previous validated release
until the new one has passed browser smoke tests and can serve as a rollback.

## Literature retrieval and RAG operations

The current retrieval path is provider-neutral and multi-disease:

1. reuse eligible documents already indexed in ChromaDB;
2. process any successful local provider cache not yet indexed;
3. query keyless Europe PMC as the primary live literature source;
4. skip the disease-specific Europe PMC request when the general pool already
   has at least five eligible papers, including two for the active disease;
5. when Europe PMC and local evidence provide no usable literature, continue
   answer generation and enqueue one Semantic Scholar request capped at 10 raw
   papers; neither chatbot nor admin requests paginate a successful fallback;
6. filter gene-symbol ambiguity and biomedical relevance;
7. embed accepted documents with BGE-M3;
8. retrieve dense candidates and rerank them with MedCPT; and
9. prioritize the active disease without excluding useful evidence about other
   diseases.

General and phenotype-specific pools are query provenance, not mutually
exclusive topics. A general gene query can legitimately retrieve a paper about
the active disease. Candidate assembly deduplicates matching paper IDs before
reranking.

Runtime locations, all excluded from Git, are:

| State | Default path |
|---|---|
| ChromaDB | `chroma/` |
| Semantic Scholar cache | `cache_literature/semantic_scholar/` |
| Europe PMC cache | `cache_literature/europe_pmc/` |
| Optional session logs | `logs/` |
| Evaluation responses | `evaluation_responses/` |

Audit provider-cache eligibility metadata without sending upstream requests:

```bash
./.xprs_portal/bin/python scripts/reconcile_literature_cache.py
```

After reviewing the dry run, add `--write` to update only changed
`eligible_count` fields atomically. Stop the portal first so a provider cache
cannot be written concurrently.

### Reset runtime-generated state

This is destructive and should not be part of routine recovery. Stop the portal
first and make a backup if the indexed literature is valuable.

Always inspect the reset targets with the dry run:

```bash
./.xprs_portal/bin/python scripts/reset_runtime_state.py
```

Only after reviewing that output:

```bash
./.xprs_portal/bin/python scripts/reset_runtime_state.py --yes
```

The script clears session logs, both provider literature caches, and ChromaDB.
Plot payloads are generated in memory and require no cleanup. The script
deliberately leaves source data untouched. If the indexed
literature is valuable, move `cache_literature/` and `chroma/` to a private
backup location while the portal is stopped before confirming the reset.
Restarting recreates the required directories.

## Updating the application from GitHub

The repository uses SSH for GitHub and `main` tracks `origin/main`.

Before updating:

```bash
cd /path/to/xprs_portal
git status --short --branch
git fetch origin
git log --oneline --decorate --graph --max-count=12 --all
```

Do not pull over unexplained local changes. Commit, archive, or review them
first. For a clean fast-forward update:

```bash
git pull --ff-only origin main
```

Dependency changes require:

```bash
./.xprs_portal/bin/pip install -r requirements.txt
```

Before publishing a new public commit, run at minimum:

```bash
./.xprs_portal/bin/python -m unittest discover -s tests
./.xprs_portal/bin/python -m compileall -q agents routes scripts tests *.py
./.xprs_portal/bin/python scripts/check_public_repo.py
git diff --check
```

The public-repository scan is mandatory because it checks tracked and untracked
files for credentials, internal storage paths, K-PREDICT IDs, source RDS/TSV
artifacts, and evaluation responses. It supplements review; it does not make
private data safe to publish.

After an update, perform a controlled restart and test the landing page,
K-PREDICT access, one overview-to-dashboard navigation, summary generation, a
reference-paper dialog, and PDF download.

## Troubleshooting guide

| Symptom | Checks and response |
|---|---|
| Nothing listens on 9009 | Start the `xprs` tmux session using the emergency recovery command. |
| tmux session exits immediately | Inspect `tmux capture-pane`; common causes are a missing dependency, invalid `.env` value, missing data path, or port conflict. |
| `Address already in use` | Find the existing listener with `ss -ltnp`; do not launch a second copy. |
| Chroma says another XPRS process has it open | Locate and stop the duplicate portal/indexing process. Never remove the lock while a process is alive. |
| Startup appears frozen | Model initialization is CPU- and disk-intensive. Wait for `Application startup complete`; inspect memory and disk only if progress stops for several minutes. |
| Local HTTP works, remote browser fails | Check firewall/network exposure for 9009. Confirm Uvicorn is bound to `0.0.0.0`, not `127.0.0.1`. |
| K-PREDICT code rejected | Confirm `KPREDICT_ENABLED`, the release `manifest.json`, `KPREDICT_DATA_ROOT`, and `XPRS_KPREDICT_TOKEN`; restart after `.env` changes; reopen the fragment link. |
| Admin page returns 404 | `XPRS_ADMIN_TOKEN` is unset, invalid, or its cookie expired. Use the current fragment link. The 404 is intentional route concealment. |
| Summary has no citations | Inspect the admin retrieval coverage. The gene may have no eligible cached/indexed evidence, Europe PMC may return no qualifying papers, or the background Semantic Scholar fallback may still be queued/throttled. The portal may still summarize measured gene contributions, but it must not present an unsupported literature interpretation. |
| Semantic Scholar returns 429 | Let the shared cooldown/queue recover. Avoid parallel manual requests and repeated clicks. Europe PMC remains the primary keyless source. |
| Browser says `Failed to fetch` | Check `/healthz` and tmux output first. If healthy, retry once and inspect browser/network logs; repeated failures need endpoint-specific diagnosis rather than a blind restart. |
| PDF download fails once | Confirm the summary session still exists and K-PREDICT authorization is current. Check tmux output for the report endpoint; do not assume the browser message identifies the server cause. |
| Disk use grows | Inspect `chroma/`, provider caches, logs, and evaluation responses. Plot payloads are generated in memory and should not consume persistent storage. Archive deliberately; do not delete private or indexed evidence without a reviewed retention decision. |

Useful diagnostic commands:

```bash
df -h /path/to/xprs_portal
du -sh chroma cache_literature logs 2>/dev/null
free -h
tmux capture-pane -p -t xprs:0.0 -S -500
curl -fsS http://127.0.0.1:9009/healthz
curl -fsS http://127.0.0.1:9009/api/health/rag
```

## Post-recovery smoke-test checklist

- [ ] `/healthz` returns `{"status":"ok"}`.
- [ ] Landing page and dashboard return HTTP 200.
- [ ] 1000 Genomes overview loads its breast-cancer density view.
- [ ] Current K-PREDICT fragment link establishes access.
- [ ] K-PREDICT individual and disease selection loads overview cards.
- [ ] Dashboard density, Manhattan, and rare-variant panes render.
- [ ] A summary can start and its progress stream remains connected.
- [ ] A stored reference opens with title, journal, and abstract metadata.
- [ ] PDF report download succeeds.
- [ ] Admin document coverage loads with the current administrator token.
- [ ] No private identifiers, tokens, or raw data appear in logs or Git status.

## Recommended reliability improvement

tmux is convenient for development and demonstrations, but it does not restart
the portal after a node reboot or unexpected process failure. The next
operational improvement should be a user-level systemd service (if the login
node permits lingering user services) or an institution-approved supervisor.
It should use the same working directory, environment file, single worker, and
Uvicorn command described above. Do not add automatic multi-worker scaling:
the current embedded ChromaDB design intentionally permits one XPRS process.
