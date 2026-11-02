(() => {
  "use strict";

  const PAGE_SIZE = 100;
  const state = {
    coverage: null, inventory: null, view: "coverage", selectedGene: "",
    pool: "all", source: "all", phenotype: "", search: "", sort: "citations_desc", offset: 0,
    coverageState: "all", coveragePool: "all", requestController: null, manualQueryKey: "", checkingS2: false, lastS2Check: null, enrichmentPollTimer: null,
  };
  const byId = (id) => document.getElementById(id);
  const elements = {
    geneSearch: byId("gene-search"), geneList: byId("gene-list"), geneListStatus: byId("gene-list-status"),
    pageTitle: byId("page-title"), coverageView: byId("coverage-view"), documentsView: byId("documents-view"),
    statDocuments: byId("stat-documents"), statGenes: byId("stat-genes"), statPlanned: byId("stat-planned"),
    statPlannedDetail: byId("stat-planned-detail"), statCached: byId("stat-cached"),
    healthS2: byId("health-s2"), healthS2Detail: byId("health-s2-detail"),
    s2KeyCheck: byId("s2-key-check"),
    healthQueue: byId("health-queue"), healthQueueDetail: byId("health-queue-detail"),
    queueBacklog: byId("queue-backlog"), queueBacklogSummary: byId("queue-backlog-summary"), queueBacklogList: byId("queue-backlog-list"),
    healthRuntime: byId("health-runtime"), healthRuntimeDetail: byId("health-runtime-detail"),
    coverageState: byId("coverage-state"), coveragePool: byId("coverage-pool"),
    coverageCount: byId("coverage-count"), coverageBody: byId("coverage-table-body"), coverageEmpty: byId("coverage-empty"),
    retrievalNotice: byId("retrieval-notice"),
    poolFilter: byId("pool-filter"), sourceFilter: byId("source-filter"), phenotypeFilter: byId("phenotype-filter"), documentSearch: byId("document-search"),
    sortFilter: byId("sort-filter"), resultsCount: byId("results-count"), documentList: byId("document-list"),
    pagination: byId("pagination"), previousPage: byId("previous-page"), nextPage: byId("next-page"), pageIndicator: byId("page-indicator"),
    accessDialog: byId("admin-access-dialog"), accessForm: byId("admin-access-form"),
    accessCode: byId("admin-access-code"), accessStatus: byId("admin-access-status"), accessSubmit: byId("admin-access-submit"),
  };

  const formatNumber = (value) => new Intl.NumberFormat().format(Number(value || 0));
  const titleCase = (value) => String(value || "").replace(/\b\w/g, (letter) => letter.toLocaleUpperCase());
  const cooldownRemaining = (item) => {
    const expiresAt = Date.parse(item?.cooldown_expires_at || "");
    if (Number.isFinite(expiresAt)) return Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000));
    return item?.cooldown_active ? Math.max(0, Number(item.cooldown_remaining_seconds || 0)) : 0;
  };
  const coverageStateLabel = (value) => ({
    complete: "Evidence available",
    indexed: "Evidence available",
    cache_only: "Awaiting indexing",
    empty: "No eligible evidence",
    missing: "Not retrieved",
    partial: "Coverage incomplete",
  }[value] || value);
  const poolStateLabel = (value) => ({
    complete: "Search finished",
    indexed: "Evidence available",
    cache_only: "Awaiting indexing",
    empty: "No eligible papers",
    missing: "Not searched",
    partial: "Search incomplete",
  }[value] || value);
  const poolLabel = (pool) => ({ general: "General query", phenotype: "Phenotype query", opentargets: "Open Targets", other: "Other" }[pool] || pool);
  const sourceLabel = (source) => source === "europe_pmc" ? "Europe PMC" : source === "semanticscholar" ? "Semantic Scholar" : titleCase(source || "unknown");
  const providerStateLabel = (state) => ({
    complete: "Complete",
    incomplete: "Search incomplete",
    retrieved: "Retrieved",
    rate_limited: "Rate limited",
    auth_failed: "Key rejected",
    unavailable: "Unavailable",
    deferred: "Skipped — cooldown active",
    not_searched: "Not searched",
  }[state] || titleCase(state));

  async function fetchJson(path, signal) {
    const response = await fetch(path, { credentials: "same-origin", signal, cache: "no-store" });
    if (!response.ok) throw new Error(response.status === 404 ? "Admin index unavailable" : `HTTP ${response.status}`);
    return response.json();
  }

  function statusBadge(status, label = coverageStateLabel(status)) {
    const badge = document.createElement("span");
    badge.className = `coverage-badge ${status}`;
    const dot = document.createElement("i");
    dot.className = `status-dot ${status}`;
    badge.append(dot, document.createTextNode(label));
    return badge;
  }

  function poolDescription(pool) {
    const descriptions = {
      complete: "Eligible evidence is indexed and the configured search stopping rule was reached",
      indexed: "Eligible evidence is indexed, but additional provider searching remains available",
      cache_only: "Raw search results are cached but no eligible documents are indexed yet",
      empty: "The search stopped without finding a paper that passed the indexing rules",
      missing: "No search has been recorded for this pool",
      partial: "The provider search has not reached its stopping point",
    };
    const parts = [descriptions[pool.status] || poolStateLabel(pool.status)];
    if (pool.documents) parts.push(`${formatNumber(pool.documents)} indexed documents`);
    if (pool.cache_present) parts.push(`${formatNumber(pool.eligible_count)} of ${formatNumber(pool.evidence_target)} unique eligible papers needed for the interactive target`);
    if (pool.cache_present) parts.push(`${formatNumber(pool.paper_count)} cached papers`);
    if (pool.raw_examined) parts.push(`${formatNumber(pool.raw_examined)} raw results examined`);
    if (pool.search_strategy_count > 1) {
      parts.push(`${formatNumber(pool.search_strategies_complete)} of ${formatNumber(pool.search_strategy_count)} search strategies complete`);
    }
    if (pool.enrichment_stop_reason) parts.push(`stop: ${pool.enrichment_stop_reason}`);
    if (pool.incomplete_providers?.length) parts.push(`unfinished: ${pool.incomplete_providers.map((source) => source === "europe_pmc" ? "Europe PMC" : "Semantic Scholar").join(", ")}`);
    if (pool.sources?.length) parts.push(`sources: ${pool.sources.map((item) => item.source === "europe_pmc" ? "Europe PMC" : "Semantic Scholar").join(", ")}`);
    return parts.join(" · ");
  }

  function pendingJobForPool(gene, pool) {
    const jobs = state.coverage?.queue?.jobs || [];
    const phenotype = String(pool.phenotype || "").toLocaleLowerCase();
    return jobs.find((job) => (
      job.gene === gene
      && job.pool_type === (phenotype ? "phenotype" : "general")
      && String(job.phenotype || "").toLocaleLowerCase() === phenotype
    ));
  }

  function providerStatusList(pool) {
    const list = document.createElement("div");
    list.className = "provider-status-list";
    for (const provider of pool.provider_statuses || []) {
      const row = document.createElement("div");
      row.className = `provider-status ${provider.state}`;
      const name = document.createElement("span");
      const dot = document.createElement("i");
      const label = document.createElement("strong");
      dot.setAttribute("aria-hidden", "true");
      label.textContent = sourceLabel(provider.source);
      name.append(dot, label);

      const status = document.createElement("small");
      const attempt = provider.last_attempt || {};
      const details = [];
      if (attempt.http_status >= 400) details.push(`HTTP ${attempt.http_status}`);
      if (provider.cache_present) {
        details.push(provider.eligible_count
          ? `${formatNumber(provider.eligible_count)} eligible`
          : provider.terminal ? "No eligible papers" : "No eligible papers yet");
      }
      status.textContent = [providerStateLabel(provider.state), ...details].join(" · ");
      row.append(name, status);

      const tooltip = [];
      if (attempt.attempted_at) tooltip.push(`Last attempt: ${new Date(attempt.attempted_at).toLocaleString()}`);
      if (attempt.detail) tooltip.push(attempt.detail);
      if (attempt.retry_after_seconds != null) tooltip.push(`Retry-After: ${attempt.retry_after_seconds}s`);
      if (!attempt.attempted_at && provider.retrieved_at) tooltip.push(`Cache retrieved: ${new Date(provider.retrieved_at).toLocaleString()}`);
      if (tooltip.length) row.title = tooltip.join(" · ");
      list.appendChild(row);
    }
    return list;
  }

  function poolCell(pool, gene) {
    const wrap = document.createElement("div");
    wrap.className = "pool-cell";
    wrap.title = poolDescription(pool);
    const pendingJob = pendingJobForPool(gene, pool);
    wrap.appendChild(statusBadge(pool.status, poolStateLabel(pool.status)));
    const detail = document.createElement("small");
    if (pool.documents) {
      detail.textContent = pool.status === "complete"
        ? `${formatNumber(pool.documents)} indexed docs · ${pool.completion_reason === "evidence_target" ? "target reached" : "providers exhausted"}`
        : `${formatNumber(pool.documents)} indexed docs · search can continue`;
    } else if (pool.status === "empty") {
      detail.textContent = `${formatNumber(pool.raw_examined || pool.paper_count)} results screened`;
    } else if (pool.cache_present) detail.textContent = `${formatNumber(pool.paper_count)} cached results`;
    else detail.textContent = "Not requested";
    wrap.appendChild(detail);
    if (pool.provider_statuses?.length) wrap.appendChild(providerStatusList(pool));
    if (["missing", "partial", "cache_only", "indexed"].includes(pool.status)) {
      const key = `${gene}::${pool.phenotype || "general"}`;
      const action = document.createElement("button");
      action.type = "button";
      action.className = "query-button";
      const canContinue = Boolean(pool.incomplete_providers?.length);
      const hasIndexableCache = Number(pool.eligible_count || 0) > 0 && !pool.documents;
      action.textContent = pendingJob
        ? pendingJob.state === "queued" ? "Queued" : "In progress"
        : hasIndexableCache ? "Index cache"
          : canContinue ? "Continue search" : "Search sources";
      action.title = pendingJob
        ? `${pendingJob.query} is already ${pendingJob.state === "queued" ? "queued" : "being handled"}`
        : hasIndexableCache
          ? "Index eligible papers already present in the provider cache"
          : canContinue
            ? "Request one additional provider search page"
            : "Search the configured literature providers and index eligible results";
      action.disabled = Boolean(pendingJob) || Boolean(state.manualQueryKey) || state.checkingS2;
      action.addEventListener("click", (event) => {
        event.stopPropagation();
        runManualQuery(gene, pool, key);
      });
      wrap.appendChild(action);
    }
    return wrap;
  }

  function renderSummary() {
    const summary = state.coverage.summary;
    elements.statDocuments.textContent = formatNumber(summary.indexed_documents);
    elements.statGenes.textContent = formatNumber(summary.indexed_genes);
    elements.statPlanned.textContent = `${formatNumber(summary.tracked_indexed_pools)} / ${formatNumber(summary.tracked_query_pools)}`;
    elements.statPlannedDetail.textContent = `${formatNumber(summary.tracked_terminal_pools)} searches finished`;
    elements.statCached.textContent = formatNumber(summary.cached_query_pools);

    const s2 = state.coverage.semantic_scholar || {};
    const s2Status = s2.api_key_status === "rate_limited" ? "Check rate limited" : s2.api_key_status === "ok" ? "Key accepted" : s2.api_key_status === "forbidden" ? "Key rejected" : s2.api_key_status === "error" ? "Check unavailable" : s2.api_key_present ? "Not yet checked" : "No API key";
    elements.healthS2.textContent = s2Status;
    elements.healthS2.dataset.tone = ["rate_limited", "forbidden", "error"].includes(s2.api_key_status) ? "warning" : s2.api_key_status === "ok" ? "good" : "neutral";
    const checkedAt = state.lastS2Check?.checked_at ? ` · Checked ${new Date(state.lastS2Check.checked_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : "";
    elements.healthS2Detail.textContent = `${s2.effective_mode === "api_key" ? "API-key mode" : "Public mode"}${s2.last_status_code ? ` · Last check HTTP ${s2.last_status_code}` : ""}${checkedAt}`;
    elements.s2KeyCheck.disabled = state.checkingS2 || Boolean(state.manualQueryKey);
    elements.s2KeyCheck.textContent = state.checkingS2 ? "Checking…" : "Check API key";

    const queue = state.coverage.queue || {};
    const queued = Number(queue.pending_jobs || 0);
    elements.healthQueue.textContent = queued ? `${formatNumber(queued)} pending` : "Idle";
    elements.healthQueue.dataset.tone = queued ? "warning" : "good";
    elements.healthQueueDetail.textContent = queue.worker_alive === false
      ? "Worker is not running"
      : `One page per action · ${queue.targets?.api_key_min_interval_seconds || "—"}s Semantic Scholar request spacing`;
    const jobs = queue.jobs || [];
    elements.queueBacklog.hidden = jobs.length === 0;
    elements.queueBacklogSummary.textContent = jobs.length === 1 ? "View 1 request" : `View ${formatNumber(jobs.length)} requests`;
    elements.queueBacklogList.replaceChildren();
    for (const job of jobs) {
      const item = document.createElement("li");
      const query = document.createElement("code");
      const jobState = document.createElement("em");
      query.textContent = job.query;
      query.title = job.query;
      jobState.textContent = job.state === "queued" ? "Queued" : job.state === "waiting" ? "Starting" : "Active";
      item.append(query, jobState);
      elements.queueBacklogList.appendChild(item);
    }

    const runtimeStates = state.coverage.runtime_cooldowns || [];
    const cooldowns = runtimeStates.filter((item) => cooldownRemaining(item) > 0);
    const longest = cooldowns.reduce((maximum, item) => Math.max(maximum, cooldownRemaining(item)), 0);
    const latest = [...runtimeStates]
      .filter((item) => item.last_query)
      .sort((left, right) => String(right.last_attempted_at || "").localeCompare(String(left.last_attempted_at || "")))[0];
    elements.healthRuntime.textContent = cooldowns.length ? `${formatNumber(longest)}s remaining` : "Clear";
    elements.healthRuntime.dataset.tone = cooldowns.length ? "warning" : "good";
    elements.healthRuntimeDetail.textContent = cooldowns.length
      ? `Applies to all Semantic Scholar fallback requests${latest?.last_query ? ` · Last query: ${latest.last_query}` : ""}`
      : latest?.last_query ? `No active pause · Last query: ${latest.last_query}` : "No in-process rate-limit pause";

  }

  function populateCoveragePools() {
    while (elements.coveragePool.options.length > 2) elements.coveragePool.remove(2);
    const phenotypes = new Set();
    for (const row of state.coverage.genes) {
      for (const pool of row.pools) if (pool.phenotype) phenotypes.add(pool.phenotype);
      for (const covered of row.covered_by_general || []) phenotypes.add(covered.phenotype);
    }
    for (const phenotype of [...phenotypes].sort()) {
      const option = document.createElement("option");
      option.value = phenotype; option.textContent = titleCase(phenotype);
      elements.coveragePool.appendChild(option);
    }
  }

  function filteredCoverageRows() {
    const needle = elements.geneSearch.value.trim().toLocaleUpperCase();
    return state.coverage.genes.filter((row) => {
      if (needle && !row.gene.includes(needle)) return false;
      if (state.coverageState !== "all" && row.coverage_state !== state.coverageState && !row.pools.some((pool) => pool.status === state.coverageState)) return false;
      if (state.coveragePool === "general" && !row.pools.some((pool) => !pool.phenotype)) return false;
      if (!['all', 'general'].includes(state.coveragePool)
          && !row.pools.some((pool) => pool.phenotype === state.coveragePool)
          && !(row.covered_by_general || []).some((covered) => covered.phenotype === state.coveragePool)) return false;
      return true;
    });
  }

  function renderCoverageTable() {
    if (!state.coverage) return;
    const rows = filteredCoverageRows();
    elements.coverageBody.replaceChildren();
    elements.coverageCount.textContent = `${formatNumber(rows.length)} genes`;
    elements.coverageEmpty.hidden = rows.length > 0;
    for (const row of rows) {
      const tr = document.createElement("tr");
      tr.tabIndex = 0; tr.title = `Open indexed documents for ${row.gene}`;
      const gene = document.createElement("td");
      const geneButton = document.createElement("button");
      geneButton.className = "table-gene"; geneButton.type = "button"; geneButton.textContent = row.gene;
      gene.appendChild(geneButton);

      const general = document.createElement("td");
      const generalPool = row.pools.find((pool) => !pool.phenotype);
      if (generalPool) general.appendChild(poolCell(generalPool, row.gene)); else general.textContent = "—";

      const phenotype = document.createElement("td");
      const phenotypePools = row.pools.filter((pool) => pool.phenotype);
      const coveredByGeneral = row.covered_by_general || [];
      if (phenotypePools.length || coveredByGeneral.length) {
        const stack = document.createElement("div"); stack.className = "phenotype-stack";
        for (const pool of phenotypePools) {
          const item = document.createElement("div");
          const label = document.createElement("span"); label.textContent = titleCase(pool.phenotype);
          item.append(label, poolCell(pool, row.gene)); stack.appendChild(item);
        }
        for (const covered of coveredByGeneral) {
          const item = document.createElement("div");
          const label = document.createElement("span"); label.textContent = titleCase(covered.phenotype);
          const coverage = document.createElement("div"); coverage.className = "pool-cell general-coverage";
          coverage.title = `The general query already contains ${formatNumber(covered.documents)} eligible papers associated with ${covered.phenotype}; a separate disease query was not needed.`;
          coverage.appendChild(statusBadge("complete", "Covered by general query"));
          const detail = document.createElement("small");
          detail.textContent = `${formatNumber(covered.documents)} disease-related docs in general pool`;
          coverage.appendChild(detail);
          item.append(label, coverage); stack.appendChild(item);
        }
        phenotype.appendChild(stack);
      } else phenotype.textContent = "—";

      const documents = document.createElement("td"); documents.className = "numeric"; documents.textContent = formatNumber(row.documents);
      const coverage = document.createElement("td"); coverage.appendChild(statusBadge(row.coverage_state, coverageStateLabel(row.coverage_state)));
      tr.append(gene, general, phenotype, documents, coverage);
      const open = () => selectGene(row.gene, true);
      geneButton.addEventListener("click", open);
      tr.addEventListener("keydown", (event) => { if (event.key === "Enter") open(); });
      elements.coverageBody.appendChild(tr);
    }
  }

  function renderGeneList() {
    elements.geneList.replaceChildren();
    if (!state.coverage) return;
    const needle = elements.geneSearch.value.trim().toLocaleUpperCase();
    const rows = state.coverage.genes.filter((row) => row.gene.includes(needle));
    elements.geneListStatus.textContent = `${formatNumber(rows.length)} of ${formatNumber(state.coverage.genes.length)} genes`;
    for (const row of rows) {
      const button = document.createElement("button"); button.type = "button";
      button.className = `gene-button${row.gene === state.selectedGene ? " is-selected" : ""}`;
      const label = document.createElement("span");
      const dot = document.createElement("i"); dot.className = `status-dot ${row.coverage_state}`;
      const name = document.createElement("strong"); name.textContent = row.gene;
      label.append(dot, name);
      const count = document.createElement("small"); count.textContent = `${formatNumber(row.documents)} docs`;
      button.append(label, count); button.addEventListener("click", () => selectGene(row.gene, true));
      elements.geneList.appendChild(button);
    }
    if (!rows.length) { const empty = document.createElement("p"); empty.className = "list-status"; empty.textContent = "No matching genes."; elements.geneList.appendChild(empty); }
  }

  function showView(view) {
    state.view = view;
    elements.coverageView.hidden = view !== "coverage";
    elements.documentsView.hidden = view !== "documents";
    elements.pageTitle.textContent = view === "coverage" ? "Literature retrieval" : (state.selectedGene ? `${state.selectedGene} documents` : "Indexed documents");
    document.querySelectorAll("[data-view]").forEach((button) => button.classList.toggle("is-active", button.dataset.view === view));
    const url = new URL(window.location.href); url.searchParams.set("view", view);
    if (state.selectedGene) url.searchParams.set("gene", state.selectedGene);
    history.replaceState(null, "", `${url.pathname}${url.search}`);
  }

  function selectGene(gene, switchView = false) {
    if (!gene) return;
    state.selectedGene = gene; state.offset = 0;
    renderGeneList(); populatePhenotypeFilter();
    if (switchView) showView("documents");
    if (state.view === "documents") { elements.pageTitle.textContent = `${gene} documents`; loadDocuments(); }
  }

  function populatePhenotypeFilter() {
    const row = state.inventory?.genes.find((item) => item.gene === state.selectedGene);
    const phenotypes = row?.phenotypes || {}; const available = Object.keys(phenotypes);
    if (state.phenotype && !available.includes(state.phenotype)) state.phenotype = "";
    elements.phenotypeFilter.replaceChildren();
    const all = document.createElement("option"); all.value = ""; all.textContent = available.length ? "All query phenotypes" : "No phenotype pools"; elements.phenotypeFilter.appendChild(all);
    for (const value of available) { const option = document.createElement("option"); option.value = value; option.textContent = `${titleCase(value)} (${formatNumber(phenotypes[value])})`; elements.phenotypeFilter.appendChild(option); }
    elements.phenotypeFilter.value = state.phenotype;
    elements.phenotypeFilter.disabled = !available.length || !["all", "phenotype"].includes(state.pool);
  }

  function renderLoading() {
    elements.documentList.setAttribute("aria-busy", "true"); elements.documentList.replaceChildren();
    const loading = document.createElement("div"); loading.className = "loading-state"; loading.textContent = "Loading indexed documents…"; elements.documentList.appendChild(loading); elements.pagination.hidden = true;
  }
  function renderError(message) {
    elements.documentList.setAttribute("aria-busy", "false"); elements.documentList.replaceChildren();
    const error = document.createElement("div"); error.className = "error-state"; error.textContent = message; elements.documentList.appendChild(error); elements.resultsCount.textContent = "Unable to load documents"; elements.pagination.hidden = true;
  }
  function badge(text, className = "") { const item = document.createElement("span"); item.className = `badge ${className}`.trim(); item.textContent = text; return item; }
  function appendEntity(line, label, value) { if (!value) return; const chip = document.createElement("span"); chip.textContent = `${label}: ${value}`; line.appendChild(chip); }

  function renderDocumentCard(item) {
    const card = document.createElement("article"); card.className = "document-card";
    const header = document.createElement("div"); header.className = "document-card-header";
    const titleArea = document.createElement("div"); const badges = document.createElement("div"); badges.className = "badges"; badges.appendChild(badge(poolLabel(item.pool), item.pool)); if (item.phenotype) badges.appendChild(badge(item.phenotype, "phenotype"));
    const heading = document.createElement("h2"); heading.className = "document-title";
    if (item.url && /^https?:\/\//i.test(item.url)) { const link = document.createElement("a"); link.href = item.url; link.target = "_blank"; link.rel = "noreferrer"; link.textContent = item.title; heading.appendChild(link); } else heading.textContent = item.title;
    titleArea.append(badges, heading);
    const citations = document.createElement("div"); citations.className = "citation-count"; const value = document.createElement("strong"); value.textContent = item.citation_count == null ? "—" : formatNumber(item.citation_count); citations.append(value, document.createTextNode("citations")); header.append(titleArea, citations); card.appendChild(header);
    const sourceLabel = item.source === "europe_pmc" ? "Europe PMC" : item.source === "semanticscholar" ? "Semantic Scholar" : titleCase(item.source || "unknown");
    const meta = document.createElement("p"); meta.className = "metadata-line"; meta.textContent = [sourceLabel, item.journal, item.phenotype ? `Phenotype: ${item.phenotype}` : "", item.paper_id ? `ID: ${item.paper_id}` : ""].filter(Boolean).join(" · "); card.appendChild(meta);
    const entityLine = document.createElement("div"); entityLine.className = "entity-line"; appendEntity(entityLine, "Genes", item.extracted_genes); appendEntity(entityLine, "Phenotypes", item.extracted_phenotypes); if (entityLine.childElementCount) card.appendChild(entityLine);
    const details = document.createElement("details"); details.className = "indexed-text"; const summary = document.createElement("summary"); summary.textContent = "View indexed text"; const body = document.createElement("pre"); body.textContent = item.document || "No stored text."; details.append(summary, body); card.appendChild(details); return card;
  }

  function renderDocuments(data) {
    elements.documentList.setAttribute("aria-busy", "false"); elements.documentList.replaceChildren();
    const start = data.total ? data.offset + 1 : 0; const end = Math.min(data.offset + data.documents.length, data.total);
    elements.resultsCount.textContent = data.total ? `Showing ${formatNumber(start)}–${formatNumber(end)} of ${formatNumber(data.total)} documents` : "No documents match these filters";
    if (!data.documents.length) { const empty = document.createElement("div"); empty.className = "empty-state"; empty.textContent = "No indexed documents match the selected gene and filters."; elements.documentList.appendChild(empty); }
    else for (const item of data.documents) elements.documentList.appendChild(renderDocumentCard(item));
    const pages = Math.max(1, Math.ceil(data.total / data.limit)); const page = Math.floor(data.offset / data.limit) + 1;
    elements.pagination.hidden = data.total <= data.limit; elements.previousPage.disabled = data.offset === 0; elements.nextPage.disabled = data.offset + data.limit >= data.total; elements.pageIndicator.textContent = `Page ${formatNumber(page)} of ${formatNumber(pages)}`;
  }

  async function loadDocuments() {
    if (!state.selectedGene) return;
    if (state.requestController) state.requestController.abort(); state.requestController = new AbortController(); renderLoading();
    const params = new URLSearchParams({ gene: state.selectedGene, pool: state.pool, source: state.source, phenotype: state.phenotype, search: state.search, sort: state.sort, offset: String(state.offset), limit: String(PAGE_SIZE) });
    try { renderDocuments(await fetchJson(`/api/admin/documents?${params}`, state.requestController.signal)); }
    catch (error) { if (error.name !== "AbortError") renderError(error.message || "Unable to load documents."); }
  }

  function showRetrievalNotice(message, tone) {
    elements.retrievalNotice.hidden = false;
    elements.retrievalNotice.className = `retrieval-notice ${tone || ""}`.trim();
    elements.retrievalNotice.textContent = message;
  }

  async function refreshCoverageData() {
    state.coverage = await fetchJson("/api/admin/retrieval-coverage");
    state.inventory = state.coverage.inventory;
    renderSummary();
    populateCoveragePools();
    renderGeneList();
    renderCoverageTable();
    populatePhenotypeFilter();
    scheduleEnrichmentPoll();
  }

  function scheduleEnrichmentPoll() {
    if (state.enrichmentPollTimer) clearTimeout(state.enrichmentPollTimer);
    state.enrichmentPollTimer = null;
    if (Number(state.coverage?.queue?.pending_jobs || 0) > 0) {
      state.enrichmentPollTimer = setTimeout(() => {
        refreshCoverageData().catch(() => {});
      }, 5000);
    } else if ((state.coverage?.runtime_cooldowns || []).some((item) => cooldownRemaining(item) > 0)) {
      state.enrichmentPollTimer = setTimeout(() => {
        renderSummary();
        scheduleEnrichmentPoll();
      }, 1000);
    }
  }

  async function runManualQuery(gene, pool, key) {
    if (state.manualQueryKey || state.checkingS2) return;
    state.manualQueryKey = key;
    renderSummary();
    renderCoverageTable();
    const queryLabel = pool.phenotype ? `${gene} ${pool.phenotype}` : gene;
    showRetrievalNotice(`Retrieving “${queryLabel}” from the literature providers…`, "is-loading");
    try {
      const response = await fetch("/api/admin/retrieval-query", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          gene,
          pool: pool.phenotype ? "phenotype" : "general",
          phenotype: pool.phenotype || null,
        }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json();
      const lastProgress = result.progress?.length ? result.progress[result.progress.length - 1] : "";
      if (result.status === "already_complete") {
        showRetrievalNotice(`${queryLabel}: the configured search stopping rule was already reached.`, "is-success");
      } else if (result.status === "indexed" || result.status === "already_indexed") {
        showRetrievalNotice(`${queryLabel}: documents are now indexed${result.scheduled ? "; one continuation page is queued" : ""}.`, "is-success");
      } else if (result.status === "enrichment_queued") {
        showRetrievalNotice(result.documents_present
          ? `${queryLabel}: additional retrieval is queued; the existing indexed documents remain available.`
          : `${queryLabel}: no eligible documents are indexed yet; one additional search page is queued.`, "is-neutral");
      } else if (result.status === "enrichment_pending") {
        showRetrievalNotice(result.documents_present
          ? `${queryLabel}: additional retrieval is already queued or in progress; the existing indexed documents remain available.`
          : `${queryLabel}: no eligible cached documents were found; an existing background retrieval may still be in progress.`, "is-neutral");
      } else if (result.status === "no_eligible_documents") {
        showRetrievalNotice(`${queryLabel}: retrieval stopped without finding a paper that passed the indexing rules.`, "is-neutral");
      } else {
        showRetrievalNotice(lastProgress || `${queryLabel}: the literature providers are currently unavailable.`, "is-error");
      }
      await refreshCoverageData();
    } catch (error) {
      showRetrievalNotice(`Could not retrieve ${queryLabel}: ${error.message || "request failed"}.`, "is-error");
    } finally {
      state.manualQueryKey = "";
      renderSummary();
      renderCoverageTable();
    }
  }

  async function runS2KeyCheck() {
    if (state.checkingS2 || state.manualQueryKey) return;
    state.checkingS2 = true;
    renderSummary();
    renderCoverageTable();
    showRetrievalNotice("Checking the configured Semantic Scholar API key with one keyed request…", "is-loading");
    try {
      const response = await fetch("/api/admin/semanticscholar-check", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json();
      state.lastS2Check = result;
      if (result.status === "ok") {
        showRetrievalNotice("Semantic Scholar accepted the configured API key. Gene searches can still be throttled independently; their latest results are shown per query pool.", "is-success");
      } else if (result.status === "invalid") {
        showRetrievalNotice("Semantic Scholar rejected the configured API key.", "is-error");
      } else if (result.status === "rate_limited") {
        showRetrievalNotice("The keyed request was rate-limited. Key validity is inconclusive; try again after the cooldown.", "is-neutral");
      } else if (result.status === "missing") {
        showRetrievalNotice("No Semantic Scholar API key is configured.", "is-error");
      } else {
        showRetrievalNotice("Semantic Scholar could not be reached. Key validity is inconclusive.", "is-neutral");
      }
      await refreshCoverageData();
    } catch (error) {
      showRetrievalNotice(`Could not check the Semantic Scholar API key: ${error.message || "request failed"}.`, "is-error");
    } finally {
      state.checkingS2 = false;
      renderSummary();
      renderCoverageTable();
    }
  }

  async function loadCoverage() {
    try {
      await refreshCoverageData();
      const url = new URL(window.location.href); const requestedGene = url.searchParams.get("gene");
      const initial = state.coverage.genes.find((row) => row.gene === requestedGene) || state.coverage.genes.find((row) => row.documents > 0) || state.coverage.genes[0];
      if (initial) selectGene(initial.gene, false);
      const requestedView = url.searchParams.get("view");
      showView(requestedGene || requestedView === "documents" ? "documents" : "coverage");
      if (state.view === "documents" && state.selectedGene) loadDocuments();
    } catch (error) { elements.geneListStatus.textContent = error.message || "Unable to load index."; renderError(error.message || "Unable to load retrieval coverage."); }
  }

  async function submitAccessCode(token) {
    return fetch("/api/admin/access", {
      method: "POST",
      credentials: "same-origin",
      headers: token ? { "X-XPRS-Admin-Token": token } : {},
      cache: "no-store",
    });
  }

  function clearAccessFragment() {
    if (!window.location.hash) return;
    const url = new URL(window.location.href);
    url.hash = "";
    history.replaceState(null, "", `${url.pathname}${url.search}`);
  }

  function requestAccessCode() {
    return new Promise((resolve) => {
      elements.accessStatus.textContent = "";
      if (typeof elements.accessDialog.showModal === "function") elements.accessDialog.showModal();
      else elements.accessDialog.setAttribute("open", "");
      window.setTimeout(() => elements.accessCode.focus(), 0);

      elements.accessForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const token = elements.accessCode.value.trim();
        if (!token) return;
        elements.accessSubmit.disabled = true;
        elements.accessStatus.textContent = "Checking access code…";
        try {
          const response = await submitAccessCode(token);
          if (!response.ok) {
            elements.accessStatus.textContent = "The admin access code was not accepted.";
            elements.accessCode.select();
            return;
          }
          elements.accessCode.value = "";
          elements.accessStatus.textContent = "";
          elements.accessDialog.close();
          resolve();
        } catch (_error) {
          elements.accessStatus.textContent = "Unable to verify the access code. Please try again.";
        } finally {
          elements.accessSubmit.disabled = false;
        }
      });
    });
  }

  async function establishAccess() {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const token = fragment.get("token") || "";
    try {
      const response = await submitAccessCode(token);
      if (token) clearAccessFragment();
      if (response.ok) return;
    } catch (_error) {
      if (token) clearAccessFragment();
    }
    await requestAccessCode();
  }

  document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => { showView(button.dataset.view); if (button.dataset.view === "documents" && state.selectedGene) loadDocuments(); }));
  elements.accessDialog.addEventListener("cancel", (event) => event.preventDefault());
  elements.s2KeyCheck.addEventListener("click", runS2KeyCheck);
  elements.geneSearch.addEventListener("input", () => { renderGeneList(); renderCoverageTable(); });
  elements.coverageState.addEventListener("change", () => { state.coverageState = elements.coverageState.value; renderCoverageTable(); });
  elements.coveragePool.addEventListener("change", () => { state.coveragePool = elements.coveragePool.value; renderCoverageTable(); });
  elements.poolFilter.addEventListener("change", () => { state.pool = elements.poolFilter.value; if (!["all", "phenotype"].includes(state.pool)) state.phenotype = ""; populatePhenotypeFilter(); state.offset = 0; loadDocuments(); });
  elements.sourceFilter.addEventListener("change", () => { state.source = elements.sourceFilter.value; state.offset = 0; loadDocuments(); });
  elements.phenotypeFilter.addEventListener("change", () => { state.phenotype = elements.phenotypeFilter.value; if (state.phenotype) { state.pool = "phenotype"; elements.poolFilter.value = "phenotype"; } populatePhenotypeFilter(); state.offset = 0; loadDocuments(); });
  elements.sortFilter.addEventListener("change", () => { state.sort = elements.sortFilter.value; state.offset = 0; loadDocuments(); });
  let searchTimer; elements.documentSearch.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { state.search = elements.documentSearch.value.trim(); state.offset = 0; loadDocuments(); }, 250); });
  elements.previousPage.addEventListener("click", () => { state.offset = Math.max(0, state.offset - PAGE_SIZE); loadDocuments(); });
  elements.nextPage.addEventListener("click", () => { state.offset += PAGE_SIZE; loadDocuments(); });

  establishAccess().then(loadCoverage).catch((error) => { elements.geneListStatus.textContent = error.message || "Unable to access index."; renderError(error.message || "Unable to access the retrieval index."); });
})();
