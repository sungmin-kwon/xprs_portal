let allIndividuals = [];
let diseases = [];
let cohorts = [];
let selectedCohortSlug = "1000_genomes";
let selectedIndividualId = "";
let currentLanguage = "en";
let currentTheme = "light";
let cohortsLoaded = false;
let individualsLoaded = false;
let diseasesLoaded = false;
let visibleDiseaseCards = [];

const LANGUAGE_PREFERENCE_KEY = "xprs.language";
const THEME_PREFERENCE_KEY = "xprs.theme";
const INDIVIDUAL_PREFERENCE_KEY = "xprs.individual_id";

const UI_TEXT = {
  en: {
    documentTitle: "XPRS Disease Overview",
    diseaseNavigation: "Disease navigation",
    portalTitle: "XPRS Portal",
    diseaseOverview: "Disease overview",
    breastCancerPortal: "Breast cancer portal",
    userEvaluation: "User evaluation survey",
    pageTitle: "XPRS Disease Overview",
    aboutXprs: "About XPRS",
    cohortAndIndividual: "Cohort & Individual",
    cohort: "Cohort",
    availableCohorts: "Available cohorts",
    individualId: "ID",
    searchIndividualId: "Search individual ID",
    availableIndividualIds: "Available individual IDs",
    riskOverview: "Overall Individual Risk Overview",
    refreshRiskCards: "Refresh risk cards",
    switchToKorean: "Switch to Korean",
    switchToEnglish: "Switch to English",
    darkMode: "Dark mode",
    lightMode: "Light mode",
    loadingCohorts: "Loading cohorts...",
    loadingIndividuals: "Loading individuals...",
    loadingDiseaseWorkspaces: "Loading disease workspaces...",
    loadingRiskCards: "Loading risk density cards...",
    noDiseaseWorkspaces: "No disease workspaces are configured.",
    noModelData: "No data available yet.",
    modelDataUnavailable: "No data available for this disease.",
    cohortDataUnavailable: "No data available for this cohort.",
    available: "Available",
    unavailable: "Unavailable",
    percentile: "Percentile",
    portalLoadFailed: "Failed to load portal data",
    individualCount: (count) => `${count} individual${count === 1 ? "" : "s"} available`,
    failedToLoadCohorts: (status) => `Failed to load cohorts: HTTP ${status}`,
    failedToLoadDiseases: (status) => `Failed to load diseases: HTTP ${status}`,
    failedToLoadIndividuals: (status) => `Failed to load individuals: HTTP ${status}`,
  },
  ko: {
    documentTitle: "XPRS 질환 위험 개요",
    diseaseNavigation: "질환 탐색",
    portalTitle: "XPRS 포털",
    diseaseOverview: "질환 위험 개요",
    breastCancerPortal: "유방암 포털",
    userEvaluation: "사용성 평가 설문",
    pageTitle: "XPRS 질환 위험 개요",
    aboutXprs: "XPRS 소개",
    cohortAndIndividual: "코호트 및 개인",
    cohort: "코호트",
    availableCohorts: "선택 가능한 코호트",
    individualId: "개인 ID",
    searchIndividualId: "개인 ID 검색",
    availableIndividualIds: "선택 가능한 개인 ID",
    riskOverview: "개인별 질환 위험 개요",
    refreshRiskCards: "위험 카드 새로고침",
    switchToKorean: "한국어로 전환",
    switchToEnglish: "영어로 전환",
    darkMode: "다크 모드",
    lightMode: "라이트 모드",
    loadingCohorts: "코호트 불러오는 중...",
    loadingIndividuals: "개인 ID 불러오는 중...",
    loadingDiseaseWorkspaces: "질환별 작업공간 불러오는 중...",
    loadingRiskCards: "위험 분포 카드 불러오는 중...",
    noDiseaseWorkspaces: "구성된 질환별 작업공간이 없습니다.",
    noModelData: "아직 사용할 수 있는 데이터가 없습니다.",
    modelDataUnavailable: "이 질환에는 사용할 수 있는 데이터가 없습니다.",
    cohortDataUnavailable: "이 코호트에는 사용할 수 있는 데이터가 없습니다.",
    available: "이용 가능",
    unavailable: "이용 불가",
    percentile: "백분위",
    portalLoadFailed: "포털 데이터를 불러오지 못했습니다",
    individualCount: (count) => `사용 가능한 개인 ID ${count}개`,
    failedToLoadCohorts: (status) => `코호트를 불러오지 못했습니다: HTTP ${status}`,
    failedToLoadDiseases: (status) => `질환 목록을 불러오지 못했습니다: HTTP ${status}`,
    failedToLoadIndividuals: (status) => `개인 ID를 불러오지 못했습니다: HTTP ${status}`,
  },
};

const DISEASE_NAMES_KO = {
  breast_cancer: "유방암",
  type2_diabetes: "제2형 당뇨병",
  gastric_cancer: "위암",
  colorectal_cancer: "대장암",
  uterine_cancer: "자궁암",
  thyroid_cancer: "갑상선암",
  prostate_cancer: "전립선암",
  pancreatic_cancer: "췌장암",
};

const $ = (id) => document.getElementById(id);

function t(key, ...args) {
  const bundle = UI_TEXT[currentLanguage] || UI_TEXT.en;
  const value = bundle[key] ?? UI_TEXT.en[key] ?? key;
  return typeof value === "function" ? value(...args) : value;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function setText(id, value) {
  const el = $(id);
  if (el) el.textContent = value || "";
}

function readPreference(key, fallback) {
  try {
    return window.localStorage.getItem(key) || fallback;
  } catch (_error) {
    return fallback;
  }
}

function savePreference(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch (_error) {
    // The portal remains usable when storage is disabled by the browser.
  }
}

function syncEvaluationAvailability(enabled) {
  document.querySelectorAll("[data-evaluation-link]").forEach((link) => {
    link.hidden = !enabled;
    link.style.display = enabled ? "" : "none";
  });
}

async function loadAppInfo() {
  try {
    const response = await fetch("/api/info");
    if (!response.ok) return;
    const data = await response.json();
    syncEvaluationAvailability(data.evaluation_enabled === true);
  } catch (_error) {
    syncEvaluationAvailability(false);
  }
}

function getSelectedCohort() {
  return cohorts.find((cohort) => cohort.slug === selectedCohortSlug) || null;
}

function cohortDisplayLabel(cohort) {
  if (!cohort) return "";
  if (currentLanguage !== "ko") return cohort.display_label || cohort.name || "";
  const access = cohort.access === "private" ? "비공개" : "공개";
  return `${cohort.name} (${access})`;
}

function diseaseDisplayName(card) {
  if (currentLanguage === "ko") {
    return DISEASE_NAMES_KO[card.slug] || card.display_name;
  }
  return card.display_name;
}

function unavailableReason(card) {
  const cohort = getSelectedCohort();
  if (cohort && !cohort.data_available) return t("cohortDataUnavailable");
  return card.unavailable_reason ? t("modelDataUnavailable") : t("noModelData");
}

function syncLanguageToggle() {
  const button = $("language-toggle-top");
  if (!button) return;
  const label = button.querySelector(".language-toggle-label");
  if (label) label.textContent = currentLanguage === "ko" ? "KO" : "EN";
  const action = currentLanguage === "ko" ? t("switchToEnglish") : t("switchToKorean");
  button.setAttribute("aria-label", action);
  button.setAttribute("title", action);
}

function updateStaticText() {
  document.documentElement.lang = currentLanguage === "ko" ? "ko" : "en";
  document.title = t("documentTitle");

  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.setAttribute("placeholder", t(element.dataset.i18nPlaceholder));
  });
  document.querySelectorAll("[data-i18n-title]").forEach((element) => {
    element.setAttribute("title", t(element.dataset.i18nTitle));
  });
  document.querySelectorAll("[data-i18n-aria]").forEach((element) => {
    element.setAttribute("aria-label", t(element.dataset.i18nAria));
  });
  syncLanguageToggle();
  syncThemeToggle();
}

function updateGridSubtitle() {
  const cohortLabel = cohortDisplayLabel(getSelectedCohort());
  const pid = selectedIndividualId || $("individual-id")?.value || "";
  setText("grid-subtitle", pid ? `${cohortLabel} · ${pid}` : cohortLabel);
}

function applyLanguage(language) {
  currentLanguage = language === "ko" ? "ko" : "en";
  savePreference(LANGUAGE_PREFERENCE_KEY, currentLanguage);
  updateStaticText();

  if (cohortsLoaded) {
    renderCohorts();
  } else {
    setText("disease-count-status", t("loadingCohorts"));
  }
  if (individualsLoaded) {
    filterIndividuals();
  } else {
    setText("individual-status", t("loadingIndividuals"));
  }
  if (visibleDiseaseCards.length || diseasesLoaded) {
    renderDiseaseCards(visibleDiseaseCards);
  } else {
    const grid = $("disease-grid");
    if (grid) {
      grid.innerHTML = `
        <div class="empty-state">
          <span class="material-symbols-outlined" aria-hidden="true">query_stats</span>
          <p>${escapeHtml(t("loadingDiseaseWorkspaces"))}</p>
        </div>
      `;
    }
  }
  updateGridSubtitle();
}

function toggleLanguage() {
  applyLanguage(currentLanguage === "ko" ? "en" : "ko");
}

function syncThemeToggle() {
  const button = $("theme-toggle-top");
  if (!button) return;
  const icon = button.querySelector(".theme-icon");
  if (icon) icon.textContent = currentTheme === "dark" ? "☀" : "☾";
  const action = currentTheme === "dark" ? t("lightMode") : t("darkMode");
  button.setAttribute("aria-label", action);
  button.setAttribute("title", action);
}

function applyTheme(theme) {
  currentTheme = theme === "dark" ? "dark" : "light";
  savePreference(THEME_PREFERENCE_KEY, currentTheme);
  document.body.classList.toggle("dark-theme", currentTheme === "dark");
  syncThemeToggle();
  if (visibleDiseaseCards.length) renderDiseaseCards(visibleDiseaseCards);
}

function toggleTheme() {
  applyTheme(currentTheme === "dark" ? "light" : "dark");
}

async function postJSON(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return res.json();
}

function renderIndividuals(individuals) {
  const select = $("individual-id");
  if (!select) return;
  const preferred = selectedIndividualId || select.value || "";
  select.innerHTML = "";
  individuals.forEach((pid) => {
    const option = document.createElement("option");
    option.value = pid;
    option.textContent = pid;
    select.appendChild(option);
  });
  if (individuals.length) {
    select.value = individuals.includes(preferred) ? preferred : individuals[0];
    selectedIndividualId = select.value;
    if (selectedCohortSlug === "1000_genomes") {
      savePreference(INDIVIDUAL_PREFERENCE_KEY, selectedIndividualId);
    }
  } else {
    selectedIndividualId = "";
  }
  select.disabled = individuals.length === 0;
  const search = $("individual-search");
  if (search) search.disabled = individuals.length === 0;
  setText("individual-status", t("individualCount", individuals.length));
}

function renderCohorts() {
  const select = $("cohort-select");
  if (!select) return;
  select.innerHTML = "";
  cohorts.forEach((cohort) => {
    const option = document.createElement("option");
    option.value = cohort.slug;
    option.textContent = cohortDisplayLabel(cohort);
    select.appendChild(option);
  });
  if (cohorts.some((cohort) => cohort.slug === selectedCohortSlug)) {
    select.value = selectedCohortSlug;
  } else if (cohorts.length) {
    selectedCohortSlug = cohorts[0].slug;
    select.value = selectedCohortSlug;
  }
  updateCohortStatus();
}

function updateCohortStatus() {
  const cohort = getSelectedCohort();
  if (!cohort) {
    setText("disease-count-status", "");
    return;
  }
  setText("disease-count-status", cohortDisplayLabel(cohort));
}

function filterIndividuals() {
  const term = ($("individual-search")?.value || "").trim().toLowerCase();
  const filtered = term
    ? allIndividuals.filter((pid) => pid.toLowerCase().includes(term))
    : allIndividuals;
  renderIndividuals(filtered);
}

function densityCardShell(card) {
  const isAvailable = Boolean(card.enabled && card.available_for_individual && card.density);
  const tag = isAvailable ? "button" : "div";
  const disabledClass = isAvailable ? "" : " is-disabled";
  const status = isAvailable ? t("available") : t("unavailable");
  const displayName = diseaseDisplayName(card);
  const reason = unavailableReason(card);
  return `
    <${tag}
      class="disease-card${disabledClass}"
      ${isAvailable ? `type="button" data-disease="${escapeHtml(card.slug)}"` : ""}
      aria-label="${escapeHtml(displayName)}"
    >
      <div class="disease-card__header">
        <div class="disease-card__title">
          <span class="material-symbols-outlined" aria-hidden="true">${escapeHtml(card.icon || "monitoring")}</span>
          <h3>${escapeHtml(displayName)}</h3>
        </div>
        <span class="card-status">${status}</span>
      </div>
      ${
        isAvailable
          ? `<div id="mini-plot-${escapeHtml(card.slug)}" class="mini-plot"></div>`
          : `<div class="mini-plot mini-plot--unavailable"><p>${escapeHtml(reason)}</p></div>`
      }
      <div class="card-footer">
        ${
          isAvailable
            ? `<div class="card-metric"><span>${escapeHtml(t("percentile"))}</span><strong>${(Number(card.density.percentile || 0) * 100).toFixed(2)}%</strong></div>
               <div class="card-metric"><span>PRS</span><strong>${Number(card.density.prs_value || 0).toFixed(3)}</strong></div>
               <span class="material-symbols-outlined open-indicator" aria-hidden="true">arrow_forward</span>`
            : ""
        }
      </div>
    </${tag}>
  `;
}

function plotMiniDensity(card) {
  const el = $(`mini-plot-${card.slug}`);
  const density = card?.density;
  if (!el || !density || !window.Plotly) return;

  const x = density?.density?.x || [];
  const y = density?.density?.y || [];
  const prsValue = Number(density?.prs_value);
  if (!x.length || !y.length || !Number.isFinite(prsValue)) return;

  const darkTheme = currentTheme === "dark";
  const trace = {
    type: "scatter",
    mode: "lines",
    x,
    y,
    line: { color: darkTheme ? "#7bb2f6" : "#27609d", width: 2.2 },
    fill: "tozeroy",
    fillcolor: darkTheme ? "rgba(123, 178, 246, 0.16)" : "rgba(39, 96, 157, 0.10)",
    hoverinfo: "skip",
  };

  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    dragmode: false,
    margin: { l: 28, r: 12, t: 12, b: 28 },
    xaxis: {
      title: "",
      fixedrange: true,
      zeroline: false,
      showgrid: false,
      tickfont: { size: 10, color: darkTheme ? "#a9bac8" : "#66727d" },
    },
    yaxis: {
      title: "",
      fixedrange: true,
      zeroline: false,
      showgrid: true,
      gridcolor: darkTheme ? "#26364c" : "#eef2f5",
      tickfont: { size: 10, color: darkTheme ? "#a9bac8" : "#66727d" },
    },
    shapes: [{
      type: "line",
      x0: prsValue,
      x1: prsValue,
      y0: 0,
      y1: 1,
      xref: "x",
      yref: "paper",
      line: { color: "#d23f31", width: 2 },
    }],
  };

  window.Plotly.newPlot(el, [trace], layout, {
    displayModeBar: false,
    displaylogo: false,
    responsive: true,
    scrollZoom: false,
    doubleClick: false,
    staticPlot: true,
  });
}

function renderDiseaseCards(cards) {
  const grid = $("disease-grid");
  if (!grid) return;
  visibleDiseaseCards = Array.isArray(cards) ? cards : [];
  if (!cards.length) {
    grid.innerHTML = `
      <div class="empty-state">
        <span class="material-symbols-outlined" aria-hidden="true">error</span>
        <p>${escapeHtml(t("noDiseaseWorkspaces"))}</p>
      </div>
    `;
    return;
  }

  grid.innerHTML = cards.map(densityCardShell).join("");
  cards.forEach(plotMiniDensity);
}

async function loadDiseases() {
  const res = await fetch("/api/diseases");
  if (!res.ok) throw new Error(t("failedToLoadDiseases", res.status));
  const data = await res.json();
  diseases = Array.isArray(data.diseases) ? data.diseases : [];
  diseasesLoaded = true;
  updateCohortStatus();
}

async function loadCohorts() {
  const res = await fetch("/api/cohorts");
  if (!res.ok) throw new Error(t("failedToLoadCohorts", res.status));
  const data = await res.json();
  cohorts = Array.isArray(data.cohorts) ? data.cohorts : [];
  selectedCohortSlug = data.default_cohort || selectedCohortSlug;
  cohortsLoaded = true;
  renderCohorts();
}

async function loadIndividuals() {
  const params = new URLSearchParams({ cohort: selectedCohortSlug });
  const res = await fetch(`/api/individuals?${params.toString()}`);
  if (!res.ok) throw new Error(t("failedToLoadIndividuals", res.status));
  const data = await res.json();
  allIndividuals = Array.isArray(data.individuals) ? data.individuals : [];
  individualsLoaded = true;
  renderIndividuals(allIndividuals);
}

async function loadDiseaseOverview() {
  const pid = selectedIndividualId || $("individual-id")?.value || "";
  if (!pid) {
    renderDiseaseCards(diseases);
    updateGridSubtitle();
    return;
  }

  selectedIndividualId = pid;
  updateGridSubtitle();
  const grid = $("disease-grid");
  if (grid) {
    grid.innerHTML = `
      <div class="empty-state">
        <span class="material-symbols-outlined" aria-hidden="true">query_stats</span>
        <p>${escapeHtml(t("loadingRiskCards"))}</p>
      </div>
    `;
  }

  try {
    const data = await postJSON("/api/disease-risk-overview", {
      individual_id: pid,
      cohort: selectedCohortSlug,
    });
    renderDiseaseCards(Array.isArray(data.diseases) ? data.diseases : []);
  } catch (err) {
    if (grid) {
      grid.innerHTML = `
        <div class="empty-state">
          <span class="material-symbols-outlined" aria-hidden="true">error</span>
          <p>${escapeHtml(err.message)}</p>
        </div>
      `;
    }
  }
}

function openDashboardForDisease(slug) {
  if (!slug || !selectedIndividualId) return;
  const params = new URLSearchParams({
    individual_id: selectedIndividualId,
    disease: slug,
    cohort: selectedCohortSlug,
    language: currentLanguage,
  });
  window.location.href = `/dashboard?${params.toString()}`;
}

window.addEventListener("DOMContentLoaded", async () => {
  applyTheme(readPreference(THEME_PREFERENCE_KEY, "light"));
  applyLanguage(readPreference(LANGUAGE_PREFERENCE_KEY, "en"));
  await loadAppInfo();

  try {
    await loadCohorts();
    await loadDiseases();
    await loadIndividuals();
    await loadDiseaseOverview();
  } catch (err) {
    setText("disease-count-status", t("portalLoadFailed"));
    setText("individual-status", err.message);
  }

  $("language-toggle-top")?.addEventListener("click", toggleLanguage);
  $("theme-toggle-top")?.addEventListener("click", toggleTheme);

  window.addEventListener("storage", (event) => {
    if (event.key === LANGUAGE_PREFERENCE_KEY && event.newValue) {
      applyLanguage(event.newValue);
    }
    if (event.key === THEME_PREFERENCE_KEY && event.newValue) {
      applyTheme(event.newValue);
    }
  });

  $("individual-search")?.addEventListener("input", () => {
    filterIndividuals();
  });

  $("cohort-select")?.addEventListener("change", async () => {
    selectedCohortSlug = $("cohort-select").value || "1000_genomes";
    selectedIndividualId = "";
    updateCohortStatus();
    await loadIndividuals();
    await loadDiseaseOverview();
  });

  $("individual-id")?.addEventListener("change", () => {
    selectedIndividualId = $("individual-id").value || "";
    if (selectedCohortSlug === "1000_genomes" && selectedIndividualId) {
      savePreference(INDIVIDUAL_PREFERENCE_KEY, selectedIndividualId);
    }
    loadDiseaseOverview();
  });

  $("refresh-grid-btn")?.addEventListener("click", () => {
    loadDiseaseOverview();
  });

  $("disease-grid")?.addEventListener("click", (event) => {
    const card = event.target?.closest?.("[data-disease]");
    if (!card) return;
    openDashboardForDisease(card.dataset.disease);
  });

  // Make the sidebar "Breast cancer portal" link deep-link with the selected
  // individual (same as its grid card) instead of the bare /dashboard, which
  // otherwise forces the individual-selection + summary-generation modal.
  // Falls back to the plain href="/dashboard" if no individual is selected.
  $("sidebar-breast-portal")?.addEventListener("click", (event) => {
    if (!selectedIndividualId) return;
    event.preventDefault();
    openDashboardForDisease("breast_cancer");
  });
});
