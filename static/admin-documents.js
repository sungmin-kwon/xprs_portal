(() => {
  "use strict";

  const PAGE_SIZE = 100;
  const state = {
    inventory: null,
    selectedGene: "",
    pool: "all",
    phenotype: "",
    search: "",
    sort: "citations_desc",
    offset: 0,
    requestController: null,
  };

  const elements = {
    geneSearch: document.getElementById("gene-search"),
    geneList: document.getElementById("gene-list"),
    geneListStatus: document.getElementById("gene-list-status"),
    pageTitle: document.getElementById("page-title"),
    statDocuments: document.getElementById("stat-documents"),
    statGenes: document.getElementById("stat-genes"),
    statGeneral: document.getElementById("stat-general"),
    statPhenotype: document.getElementById("stat-phenotype"),
    poolFilter: document.getElementById("pool-filter"),
    phenotypeFilter: document.getElementById("phenotype-filter"),
    documentSearch: document.getElementById("document-search"),
    sortFilter: document.getElementById("sort-filter"),
    resultsCount: document.getElementById("results-count"),
    documentList: document.getElementById("document-list"),
    pagination: document.getElementById("pagination"),
    previousPage: document.getElementById("previous-page"),
    nextPage: document.getElementById("next-page"),
    pageIndicator: document.getElementById("page-indicator"),
  };

  function number(value) {
    return new Intl.NumberFormat().format(Number(value || 0));
  }

  async function fetchJson(path, signal) {
    const response = await fetch(path, {
      credentials: "same-origin",
      signal,
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(response.status === 404 ? "Admin index unavailable" : `HTTP ${response.status}`);
    }
    return response.json();
  }

  function setText(element, value) {
    element.textContent = value == null || value === "" ? "—" : String(value);
  }

  function poolLabel(pool) {
    return {
      general: "General query",
      phenotype: "Phenotype query",
      opentargets: "Open Targets",
      other: "Other",
    }[pool] || pool;
  }

  function phenotypeLabel(value) {
    if (!value) return "";
    return value.replace(/\b\w/g, (letter) => letter.toLocaleUpperCase());
  }

  function populatePhenotypeFilter() {
    const row = state.inventory?.genes.find((item) => item.gene === state.selectedGene);
    const phenotypes = row?.phenotypes || {};
    const available = Object.keys(phenotypes);
    if (state.phenotype && !available.includes(state.phenotype)) {
      state.phenotype = "";
    }

    elements.phenotypeFilter.replaceChildren();
    const allOption = document.createElement("option");
    allOption.value = "";
    allOption.textContent = available.length ? "All query phenotypes" : "No phenotype pools";
    elements.phenotypeFilter.appendChild(allOption);
    for (const phenotype of available) {
      const option = document.createElement("option");
      option.value = phenotype;
      option.textContent = `${phenotypeLabel(phenotype)} (${number(phenotypes[phenotype])})`;
      elements.phenotypeFilter.appendChild(option);
    }
    elements.phenotypeFilter.value = state.phenotype;
    elements.phenotypeFilter.disabled = !available.length || !["all", "phenotype"].includes(state.pool);
  }

  function badge(text, className = "") {
    const item = document.createElement("span");
    item.className = `badge ${className}`.trim();
    item.textContent = text;
    return item;
  }

  function renderGeneList() {
    elements.geneList.replaceChildren();
    if (!state.inventory) return;

    const needle = elements.geneSearch.value.trim().toLocaleUpperCase();
    const rows = state.inventory.genes.filter((row) => row.gene.toLocaleUpperCase().includes(needle));
    elements.geneListStatus.textContent = `${number(rows.length)} of ${number(state.inventory.gene_count)} genes`;

    for (const row of rows) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `gene-button${row.gene === state.selectedGene ? " is-selected" : ""}`;
      button.setAttribute("aria-pressed", row.gene === state.selectedGene ? "true" : "false");

      const name = document.createElement("strong");
      name.textContent = row.gene;
      const count = document.createElement("small");
      count.textContent = `${number(row.total)} docs`;
      button.append(name, count);
      button.addEventListener("click", () => selectGene(row.gene));
      elements.geneList.appendChild(button);
    }

    if (!rows.length) {
      const empty = document.createElement("p");
      empty.className = "list-status";
      empty.textContent = "No matching genes.";
      elements.geneList.appendChild(empty);
    }
  }

  function updateGeneUrl() {
    const url = new URL(window.location.href);
    if (state.selectedGene) url.searchParams.set("gene", state.selectedGene);
    else url.searchParams.delete("gene");
    history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }

  function selectGene(gene) {
    if (!gene) return;
    state.selectedGene = gene;
    state.offset = 0;
    updateGeneUrl();
    renderGeneList();
    populatePhenotypeFilter();
    elements.pageTitle.textContent = `${gene} documents`;
    loadDocuments();
  }

  function renderLoading() {
    elements.documentList.setAttribute("aria-busy", "true");
    elements.documentList.replaceChildren();
    const loading = document.createElement("div");
    loading.className = "loading-state";
    loading.textContent = "Loading indexed documents…";
    elements.documentList.appendChild(loading);
    elements.pagination.hidden = true;
  }

  function renderError(message) {
    elements.documentList.setAttribute("aria-busy", "false");
    elements.documentList.replaceChildren();
    const error = document.createElement("div");
    error.className = "error-state";
    error.textContent = message;
    elements.documentList.appendChild(error);
    elements.resultsCount.textContent = "Unable to load documents";
    elements.pagination.hidden = true;
  }

  function metadataText(item) {
    const parts = [];
    if (item.journal) parts.push(item.journal);
    if (item.phenotype) parts.push(`Phenotype: ${item.phenotype}`);
    if (item.paper_id) parts.push(`S2 ID: ${item.paper_id}`);
    if (!parts.length && item.source) parts.push(`Source: ${item.source}`);
    return parts.join(" · ");
  }

  function appendEntity(entityLine, label, value) {
    if (!value) return;
    const chip = document.createElement("span");
    chip.textContent = `${label}: ${value}`;
    entityLine.appendChild(chip);
  }

  function renderDocumentCard(item) {
    const card = document.createElement("article");
    card.className = "document-card";

    const header = document.createElement("div");
    header.className = "document-card-header";
    const titleArea = document.createElement("div");
    const badges = document.createElement("div");
    badges.className = "badges";
    badges.appendChild(badge(poolLabel(item.pool), item.pool));
    if (item.phenotype) badges.appendChild(badge(item.phenotype, "phenotype"));

    const heading = document.createElement("h2");
    heading.className = "document-title";
    if (item.url && /^https?:\/\//i.test(item.url)) {
      const link = document.createElement("a");
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = item.title;
      heading.appendChild(link);
    } else {
      heading.textContent = item.title;
    }
    titleArea.append(badges, heading);

    const citations = document.createElement("div");
    citations.className = "citation-count";
    const citationValue = document.createElement("strong");
    citationValue.textContent = item.citation_count == null ? "—" : number(item.citation_count);
    citations.append(citationValue, document.createTextNode("citations"));
    header.append(titleArea, citations);
    card.appendChild(header);

    const meta = document.createElement("p");
    meta.className = "metadata-line";
    meta.textContent = metadataText(item) || "No additional citation metadata";
    card.appendChild(meta);

    const entityLine = document.createElement("div");
    entityLine.className = "entity-line";
    appendEntity(entityLine, "Genes", item.extracted_genes);
    appendEntity(entityLine, "Phenotypes", item.extracted_phenotypes);
    if (entityLine.childElementCount) card.appendChild(entityLine);

    const details = document.createElement("details");
    details.className = "indexed-text";
    const summary = document.createElement("summary");
    summary.textContent = "View indexed text";
    const body = document.createElement("pre");
    body.textContent = item.document || "No stored text.";
    details.append(summary, body);
    card.appendChild(details);
    return card;
  }

  function renderDocuments(data) {
    elements.documentList.setAttribute("aria-busy", "false");
    elements.documentList.replaceChildren();
    const start = data.total ? data.offset + 1 : 0;
    const end = Math.min(data.offset + data.documents.length, data.total);
    elements.resultsCount.textContent = data.total
      ? `Showing ${number(start)}–${number(end)} of ${number(data.total)} documents`
      : "No documents match these filters";

    if (!data.documents.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "No indexed documents match the selected gene and filters.";
      elements.documentList.appendChild(empty);
    } else {
      for (const item of data.documents) {
        elements.documentList.appendChild(renderDocumentCard(item));
      }
    }

    const pageCount = Math.max(1, Math.ceil(data.total / data.limit));
    const currentPage = Math.floor(data.offset / data.limit) + 1;
    elements.pagination.hidden = data.total <= data.limit;
    elements.previousPage.disabled = data.offset === 0;
    elements.nextPage.disabled = data.offset + data.limit >= data.total;
    elements.pageIndicator.textContent = `Page ${number(currentPage)} of ${number(pageCount)}`;
  }

  async function loadDocuments() {
    if (!state.selectedGene) return;
    if (state.requestController) state.requestController.abort();
    state.requestController = new AbortController();
    renderLoading();

    const params = new URLSearchParams({
      gene: state.selectedGene,
      pool: state.pool,
      phenotype: state.phenotype,
      search: state.search,
      sort: state.sort,
      offset: String(state.offset),
      limit: String(PAGE_SIZE),
    });
    try {
      const data = await fetchJson(`/api/admin/documents?${params}`, state.requestController.signal);
      renderDocuments(data);
    } catch (error) {
      if (error.name !== "AbortError") renderError(error.message || "Unable to load documents.");
    }
  }

  async function loadInventory() {
    try {
      const inventory = await fetchJson("/api/admin/document-inventory");
      state.inventory = inventory;
      setText(elements.statDocuments, number(inventory.document_count));
      setText(elements.statGenes, number(inventory.gene_count));
      setText(elements.statGeneral, number(inventory.pools.general || 0));
      setText(elements.statPhenotype, number(inventory.pools.phenotype || 0));
      renderGeneList();

      const requestedGene = new URL(window.location.href).searchParams.get("gene");
      const initial = inventory.genes.find((row) => row.gene === requestedGene)
        || inventory.genes[0];
      if (initial) selectGene(initial.gene);
      else renderError("The ChromaDB collection does not contain any gene documents.");
    } catch (error) {
      elements.geneListStatus.textContent = error.message || "Unable to load index.";
      renderError(error.message || "Unable to load the ChromaDB index.");
    }
  }

  async function establishAccess() {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const token = fragment.get("token") || "";
    const headers = token ? { "X-XPRS-Admin-Token": token } : {};
    const response = await fetch("/api/admin/access", {
      method: "POST",
      credentials: "same-origin",
      headers,
      cache: "no-store",
    });
    if (!response.ok) throw new Error("Admin index unavailable");
    if (token) {
      const url = new URL(window.location.href);
      url.hash = "";
      history.replaceState(null, "", `${url.pathname}${url.search}`);
    }
  }

  let searchTimer;
  elements.geneSearch.addEventListener("input", renderGeneList);
  elements.poolFilter.addEventListener("change", () => {
    state.pool = elements.poolFilter.value;
    if (!["all", "phenotype"].includes(state.pool)) {
      state.phenotype = "";
    }
    populatePhenotypeFilter();
    state.offset = 0;
    loadDocuments();
  });
  elements.phenotypeFilter.addEventListener("change", () => {
    state.phenotype = elements.phenotypeFilter.value;
    if (state.phenotype) {
      state.pool = "phenotype";
      elements.poolFilter.value = "phenotype";
    }
    populatePhenotypeFilter();
    state.offset = 0;
    loadDocuments();
  });
  elements.sortFilter.addEventListener("change", () => {
    state.sort = elements.sortFilter.value;
    state.offset = 0;
    loadDocuments();
  });
  elements.documentSearch.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.search = elements.documentSearch.value.trim();
      state.offset = 0;
      loadDocuments();
    }, 250);
  });
  elements.previousPage.addEventListener("click", () => {
    state.offset = Math.max(0, state.offset - PAGE_SIZE);
    loadDocuments();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  elements.nextPage.addEventListener("click", () => {
    state.offset += PAGE_SIZE;
    loadDocuments();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  establishAccess()
    .then(loadInventory)
    .catch((error) => {
      elements.geneListStatus.textContent = error.message || "Unable to access index.";
      renderError(error.message || "Unable to access the ChromaDB index.");
    });
})();
