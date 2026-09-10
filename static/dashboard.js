// static/dashboard.js

let activeModelName = "AI"; // Default fallback
let selectedGenerationModel = null; // user-chosen generation model id (from /api/models)
let availableModels = null; // /api/models payload
let activeSessionId = null;
let activeSummaryIndividualId = null;
let currentIndividualId = null;
let lastSelectedIndividualId = null;
let currentReferences = [];
let currentLanguage = "en";
let currentTheme = "light";
let allIndividuals = [];
let activeLoadingBubble = null;
let activeLoadingLogEl = null;
let activeLoadingAnimatedLineEl = null;
let activeLoadingAnimationTimer = null;
let activeLoadingAnimatedBaseText = "";
let geneSelectionPreviewRequestId = 0;
let currentManhattanData = null;
let currentDensityData = null;
let dashboardPlotResizeObserver = null;
let dashboardPlotResizeFrame = null;
let phenotypeLabelsKo = {};
let currentDiseaseSlug = "breast_cancer";
let diseaseRegistry = {};

const LANGUAGE_PREFERENCE_KEY = "xprs.language";
const THEME_PREFERENCE_KEY = "xprs.theme";
const INDIVIDUAL_PREFERENCE_KEY = "xprs.individual_id";

const UI_TEXT = {
  en: {
    portalTitle: "XPRS Information Portal – BREAST CANCER",
    aboutXprs: "About XPRS",
    diseaseOverview: "Disease overview",
    breastCancerPortal: "Breast cancer portal",
    userEvaluation: "User evaluation survey",
    changeIndividual: "Change Individual",
    changeIid: "Change IID",
    manhattanTitle: "Individual Manhattan Plot",
    densityTitle: "PRS Density",
    rareVariantTitle: "Rare Variant Analysis",
    rareVariantUnavailable: "Available when rare-variant data are added to a cohort",
    disclaimerTitle: "⚠️ Clinical Disclaimer",
    disclaimerBody: "This tool provides information based on statistical associations and scientific literature, and is <strong>not</strong> a diagnostic tool. Genetic risk scores are probabilistic and do not guarantee specific health outcomes. Please consult a certified genetic counselor or medical professional for clinical advice.",
    chatbotTitle: "Genetic Chatbot",
    generationModelLabel: "Answer model",
    followupPlaceholder: "Ask a question about XPRS genomics...",
    referencesList: "References List",
    noReferencesYet: "No references yet.",
    referenceViewer: "Reference Abstract Viewer",
    noPaperYet: "No paper selected yet.",
    landingEyebrow: "XPRS Information Portal: BREAST CANCER",
    landingTitle: "Configure XPRS Summary",
    individualId: "Individual ID",
    individualSearchPlaceholder: "Search Individual ID",
    geneCountLabel: "Genes to Include",
    geneCountHint: "Choose how many of this individual's highest-contributing genes to interpret in detail",
    geneCountValue: (count) => `${count} ${count === 1 ? "gene" : "genes"}`,
    genePreviewLoading: "Loading top contributing genes...",
    genePreviewNone: "No contributing genes are available.",
    genePreviewGenes: (genes) => `Genes included: [${genes.join(", ")}]`,
    citedCount: (n) => `Cited ${n}`,
    switchToKorean: "Switch to Korean",
    switchToEnglish: "Switch to English",
    darkMode: "Dark Mode",
    lightMode: "Light Mode",
    generateSummaryAlert: "No XPRS summary generated yet.",
    viewDisclaimer: "View Disclaimer",
    closeDisclaimer: "Close Disclaimer",
    cancelAction: "Cancel",
    generateSummary: "Generate Summary",
    summaryLoading: "Generating Summary...",
    loadingIndividuals: "Loading individuals...",
    loadedIndividuals: (n) => `Loaded ${n} from the 1000 Genomes Project`,
    exportLabel: "Download",
    downloadPdfReport: "Download Full PDF Report",
    downloadChatMd: "Download Chat (.md)",
    downloadChatJson: "Download Chat (.json)",
    exportUnavailable: "Generate a summary first to enable downloads.",
    exportPdfLoading: "Preparing PDF report...",
    exportChatLoading: "Preparing chat export...",
    expandPlot: "Expand plot",
    closeExpandedPlot: "Close expanded plot",
  },
  ko: {
    portalTitle: "XPRS 정보 포털 – 유방암",
    aboutXprs: "XPRS 소개",
    diseaseOverview: "질환 위험 개요",
    breastCancerPortal: "유방암 포털",
    userEvaluation: "사용성 평가 설문",
    changeIndividual: "IID 변경",
    changeIid: "IID 변경",
    manhattanTitle: "개인 맨해튼 플롯",
    densityTitle: "PRS 밀도 분포",
    rareVariantTitle: "희귀 변이 분석",
    rareVariantUnavailable: "희귀 변이 데이터가 코호트에 추가되면 이용할 수 있습니다",
    disclaimerTitle: "⚠️ 임상적 고지",
    disclaimerBody: "이 도구는 통계적 연관성과 과학 문헌을 바탕으로 정보를 제공하며, <strong>진단 도구가 아닙니다</strong>. 유전 위험 점수는 확률적 지표이며 특정 건강 결과를 보장하지 않습니다. 임상적 판단은 전문 의료진 또는 유전상담사와 상의해 주세요.",
    chatbotTitle: "유전 정보 챗봇",
    generationModelLabel: "답변 생성 모델",
    followupPlaceholder: "XPRS 유전체에 대해 질문하세요...",
    referencesList: "참고문헌 목록",
    noReferencesYet: "아직 참고문헌이 없습니다.",
    referenceViewer: "논문초록 조회",
    noPaperYet: "선택된 논문이 없습니다.",
    landingEyebrow: "XPRS 정보 포털 : 유방암",
    landingTitle: "XPRS 요약 설정",
    individualId: "Individual ID",
    individualSearchPlaceholder: "개인 ID 검색",
    geneCountLabel: "요약에 포함할 유전자 수",
    geneCountHint: "이 개인에서 기여도가 가장 높은 유전자 중 상세히 해석할 개수를 선택합니다",
    geneCountValue: (count) => `${count}개 유전자`,
    genePreviewLoading: "기여도가 높은 유전자 불러오는 중...",
    genePreviewNone: "사용 가능한 기여 유전자가 없습니다.",
    genePreviewGenes: (genes) => `포함할 유전자: [${genes.join(", ")}]`,
    citedCount: (n) => `${n}회 인용`,
    switchToKorean: "한국어로 전환",
    switchToEnglish: "영어로 전환",
    darkMode: "다크 모드",
    lightMode: "라이트 모드",
    generateSummaryAlert: "아직 XPRS 요약이 생성되지 않았습니다.",
    viewDisclaimer: "고지 보기",
    closeDisclaimer: "고지 닫기",
    cancelAction: "취소",
    generateSummary: "XPRS 요약 생성",
    summaryLoading: "요약 생성 중...",
    loadingIndividuals: "개인 목록 불러오는 중...",
    loadedIndividuals: (n) => `1000 Genomes Project 데이터에서 ${n}명의 Individual ID 적재 완료`,
    exportLabel: "내려받기",
    downloadPdfReport: "상세 PDF 보고서 내려받기",
    downloadChatMd: "채팅 내려받기 (.md)",
    downloadChatJson: "채팅 내려받기 (.json)",
    exportUnavailable: "내려받기를 사용하려면 먼저 요약을 생성하세요.",
    exportPdfLoading: "PDF 보고서를 준비하는 중...",
    exportChatLoading: "채팅 파일을 준비하는 중...",
    expandPlot: "플롯 확대",
    closeExpandedPlot: "확대 플롯 닫기",
  }
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

// ----------------------------
// Helpers
// ----------------------------
const $ = (id) => document.getElementById(id);

function dashboardUrlParams() {
  return new URLSearchParams(window.location.search || "");
}

function getActiveDiseaseMeta() {
  return diseaseRegistry[currentDiseaseSlug] || {
    slug: currentDiseaseSlug,
    display_name: currentDiseaseSlug === "breast_cancer" ? "Breast Cancer" : currentDiseaseSlug,
    short_label: currentDiseaseSlug,
    icon: "monitoring",
    enabled: currentDiseaseSlug === "breast_cancer",
  };
}

function activeDiseaseDisplayName({ upper = false } = {}) {
  const meta = getActiveDiseaseMeta();
  const name = currentLanguage === "ko"
    ? DISEASE_NAMES_KO[meta.slug] || meta.display_name || "유방암"
    : meta.display_name || "Breast Cancer";
  return upper ? name.toUpperCase() : name;
}

function getActiveDiseaseSlug() {
  return currentDiseaseSlug || "breast_cancer";
}

function t(key) {
  const bundle = UI_TEXT[currentLanguage] || UI_TEXT.en;
  const fallback = UI_TEXT.en[key];
  return bundle[key] ?? fallback ?? key;
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

function syncLanguageInUrl() {
  const url = new URL(window.location.href);
  if (url.searchParams.get("language") === currentLanguage) return;
  url.searchParams.set("language", currentLanguage);
  window.history.replaceState(
    window.history.state,
    "",
    `${url.pathname}${url.search}${url.hash}`,
  );
}

function updateUIText() {
  rememberSelectedIndividual();
  document.documentElement.lang = currentLanguage === "ko" ? "ko" : "en";

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    const value = t(key);
    if (typeof value === "string") {
      el.innerHTML = value;
    }
  });

  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.dataset.i18nPlaceholder;
    const value = t(key);
    if (typeof value === "string") {
      el.setAttribute("placeholder", value);
    }
  });

  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    const value = t(el.dataset.i18nTitle);
    if (typeof value === "string") {
      el.setAttribute("title", value);
    }
  });

  document.querySelectorAll("[data-i18n-aria]").forEach((el) => {
    const value = t(el.dataset.i18nAria);
    if (typeof value === "string") {
      el.setAttribute("aria-label", value);
    }
  });

  syncLanguageToggle();
  syncThemeButtons();
  syncIndividualSelectorButton();
  syncLandingDisclaimerButton();
  syncPlotOverlayUI();
  applyDiseaseMetadataToUI();
  updateGeneCountControl();
  restoreSelectedIndividual();
}

function applyDiseaseMetadataToUI() {
  const meta = getActiveDiseaseMeta();
  const diseaseName = activeDiseaseDisplayName();
  const diseaseNameUpper = activeDiseaseDisplayName({ upper: true });
  const titleEl = document.querySelector("[data-i18n='portalTitle']");
  const eyebrowEl = document.querySelector("[data-i18n='landingEyebrow']");
  const portalTitle = currentLanguage === "ko"
    ? `XPRS 정보 포털 – ${diseaseName}`
    : `XPRS Information Portal – ${diseaseNameUpper}`;
  if (titleEl) titleEl.textContent = portalTitle;
  if (eyebrowEl) {
    eyebrowEl.textContent = currentLanguage === "ko"
      ? `XPRS 정보 포털 : ${diseaseName}`
      : `XPRS Information Portal: ${diseaseNameUpper}`;
  }
  document.querySelectorAll("[data-disease-nav]").forEach((item) => {
    item.classList.toggle("active", item.dataset.diseaseNav === meta.slug);
  });
}

function setStatus(el, text) {
  if (!el) return;
  el.textContent = text || "";
}

function resizeVisibleDashboardPlots() {
  if (!window.Plotly?.Plots?.resize) return;
  ["density-plot", "manhattan-plot", "manhattan-plot-expanded"].forEach((id) => {
    const plot = $(id);
    if (!plot || plot.clientWidth < 1 || plot.clientHeight < 1) return;
    try {
      window.Plotly.Plots.resize(plot);
    } catch (error) {
      console.debug(`Plot resize skipped for ${id}:`, error);
    }
  });
}

function scheduleDashboardPlotResize() {
  if (dashboardPlotResizeFrame !== null) {
    window.cancelAnimationFrame(dashboardPlotResizeFrame);
  }
  dashboardPlotResizeFrame = window.requestAnimationFrame(() => {
    dashboardPlotResizeFrame = null;
    resizeVisibleDashboardPlots();
  });
}

function installDashboardPlotResizeHandling() {
  window.addEventListener("resize", scheduleDashboardPlotResize);
  if (!window.ResizeObserver) return;

  dashboardPlotResizeObserver = new ResizeObserver(scheduleDashboardPlotResize);
  [document.querySelector(".page"), document.querySelector(".viz-body")]
    .filter(Boolean)
    .forEach((element) => dashboardPlotResizeObserver.observe(element));
}

function localizePhenotypeLabel(value) {
  const raw = String(value || "").trim();
  if (!raw || currentLanguage !== "ko") return raw;
  return phenotypeLabelsKo[raw.toLowerCase()] || raw;
}

function getSelectedIndividualId() {
  return $("individual-id")?.value || "";
}

function rememberSelectedIndividual() {
  const pid = getSelectedIndividualId();
  if (pid) lastSelectedIndividualId = pid;
}

function restoreSelectedIndividual() {
  const sel = $("individual-id");
  if (!sel || !lastSelectedIndividualId) return;
  const exists = Array.from(sel.options).some((opt) => opt.value === lastSelectedIndividualId);
  if (exists) {
    sel.value = lastSelectedIndividualId;
    syncIndividualSearchDisplay(sel.value);
  }
}

function setCurrentIndividualLabel(pid) {
  const el = $("current-individual-label");
  if (el) el.textContent = pid || "—";
  syncIndividualSelectorButton();
}

function syncIndividualSelectorButton() {
  const btn = $("individual-selector-btn");
  if (!btn) return;
  const label = currentIndividualId
    ? `${t("changeIndividual")}: ${currentIndividualId}`
    : t("changeIndividual");
  btn.setAttribute("aria-label", label);
  btn.setAttribute("title", label);
}

function commitIndividualSelection(pid) {
  if (!pid) return;
  currentIndividualId = pid;
  lastSelectedIndividualId = pid;
  savePreference(INDIVIDUAL_PREFERENCE_KEY, pid);
  setCurrentIndividualLabel(pid);
  const params = new URLSearchParams({
    individual_id: pid,
    disease: getActiveDiseaseSlug(),
    language: currentLanguage,
  });
  window.history.replaceState({}, "", `/dashboard?${params.toString()}`);
}

function syncIndividualSearchDisplay(pid = getSelectedIndividualId()) {
  const input = $("individual-search");
  if (!input) return;
  input.value = pid || "";
}

function getSummaryGeneCount() {
  const input = $("summary-gene-count");
  const value = Number.parseInt(input?.value || "2", 10);
  return Math.max(1, Math.min(5, Number.isFinite(value) ? value : 2));
}

function updateGeneCountControl() {
  const count = getSummaryGeneCount();
  const input = $("summary-gene-count");
  if (input) {
    input.setAttribute("aria-valuetext", t("geneCountValue")(count));
    input.style.setProperty("--slider-progress", `${((count - 1) / 4) * 100}%`);
  }
}

function setSummaryGeneCount(count, { refresh = true } = {}) {
  const input = $("summary-gene-count");
  if (!input) return;
  input.value = String(Math.max(1, Math.min(5, Number.parseInt(count, 10) || 2)));
  updateGeneCountControl();
  if (refresh) updateGeneSelectionPreview();
}

async function updateGeneSelectionPreview() {
  const previewEl = $("gene-selection-preview");
  const pid = getSelectedIndividualId();
  if (!previewEl) return;

  if (!pid) {
    previewEl.textContent = "";
    return;
  }

  const requestId = ++geneSelectionPreviewRequestId;
  previewEl.textContent = t("genePreviewLoading");

  try {
    const res = await postJSON("/api/summary_preview", {
      individual_id: pid,
      disease: getActiveDiseaseSlug(),
      gene_count: getSummaryGeneCount(),
      language: currentLanguage,
    });
    if (requestId !== geneSelectionPreviewRequestId) return;
    const genes = Array.isArray(res?.genes) ? res.genes.filter(Boolean) : [];
    previewEl.textContent = genes.length
      ? t("genePreviewGenes")(genes)
      : t("genePreviewNone");
  } catch (_err) {
    if (requestId !== geneSelectionPreviewRequestId) return;
    previewEl.textContent = "";
  }
}

function openLandingModal() {
  if (currentIndividualId) {
    selectIndividualById(currentIndividualId);
  }
  clearLandingWarning();
  syncLandingDisclaimerButton();
  $("landing-overlay")?.classList.add("is-open");
  syncModalActivityState();
  closeIndividualDropdown();
}

function closeLandingModal(force = false) {
  if (!force && !currentIndividualId) {
    showLandingWarning();
    return;
  }
  if (!force && currentIndividualId) {
    selectIndividualById(currentIndividualId);
  }
  hideLandingDisclaimer();
  closeIndividualDropdown();
  $("landing-overlay")?.classList.remove("is-open");
  syncModalActivityState();
}

function showLandingWarning() {
  const warning = $("landing-warning");
  if (!warning) return;
  warning.textContent = t("generateSummaryAlert");
}

function clearLandingWarning() {
  const warning = $("landing-warning");
  if (!warning) return;
  warning.textContent = "";
}

function openIndividualDropdown() {
  $("landing-picker")?.classList.add("is-open");
  $("individual-dropdown")?.removeAttribute("hidden");
}

function closeIndividualDropdown() {
  $("landing-picker")?.classList.remove("is-open");
  $("individual-dropdown")?.setAttribute("hidden", "");
}

function showLandingDisclaimer() {
  $("landing-disclaimer-panel")?.removeAttribute("hidden");
  syncLandingDisclaimerButton();
}

function hideLandingDisclaimer() {
  $("landing-disclaimer-panel")?.setAttribute("hidden", "");
  syncLandingDisclaimerButton();
}

function syncModalActivityState() {
  const hasOpenModal =
    $("landing-overlay")?.classList.contains("is-open") ||
    $("plot-overlay")?.classList.contains("is-open");
  document.body.classList.toggle("modal-active", Boolean(hasOpenModal));
}

function syncPlotOverlayUI() {
  const popoutBtn = $("manhattan-popout-btn");
  if (popoutBtn) {
    popoutBtn.setAttribute("aria-label", t("expandPlot"));
    popoutBtn.setAttribute("title", t("expandPlot"));
  }
  const closeBtn = $("close-plot-overlay-btn");
  if (closeBtn) {
    closeBtn.setAttribute("aria-label", t("closeExpandedPlot"));
    closeBtn.setAttribute("title", t("closeExpandedPlot"));
  }
}

function syncManhattanPopoutButton() {
  const btn = $("manhattan-popout-btn");
  if (!btn) return;
  btn.disabled = !currentManhattanData;
}

function renderExpandedManhattanPlot() {
  if (!currentManhattanData || !$("manhattan-plot-expanded")) return;
  renderManhattanPlotly(currentManhattanData, "manhattan-plot-expanded", { expanded: true });
}

function openPlotOverlay() {
  if (!currentManhattanData) return;
  const overlay = $("plot-overlay");
  if (!overlay) return;
  overlay.classList.add("is-open");
  overlay.setAttribute("aria-hidden", "false");
  syncModalActivityState();
  window.requestAnimationFrame(() => {
    renderExpandedManhattanPlot();
    $("close-plot-overlay-btn")?.focus();
  });
}

function closePlotOverlay() {
  const overlay = $("plot-overlay");
  const expandedPlot = $("manhattan-plot-expanded");
  overlay?.classList.remove("is-open");
  overlay?.setAttribute("aria-hidden", "true");
  if (expandedPlot && window.Plotly) {
    window.Plotly.purge(expandedPlot);
  }
  syncModalActivityState();
}

function isLandingDisclaimerOpen() {
  return !$("landing-disclaimer-panel")?.hasAttribute("hidden");
}

function syncLandingDisclaimerButton() {
  const btn = $("landing-disclaimer-btn");
  if (!btn) return;
  const key = isLandingDisclaimerOpen() ? "closeDisclaimer" : "viewDisclaimer";
  btn.textContent = t(key);
}

function toggleLandingDisclaimer() {
  if (isLandingDisclaimerOpen()) {
    hideLandingDisclaimer();
  } else {
    showLandingDisclaimer();
  }
}

function syncLanguageToggle() {
  document.querySelectorAll("[data-language-option]").forEach((btn) => {
    const active = btn.dataset.languageOption === currentLanguage;
    btn.classList.toggle("is-active", active);
  });

  const btn = $("language-toggle-top");
  if (!btn) return;
  const label = btn.querySelector(".language-toggle-label");
  if (label) label.textContent = currentLanguage === "ko" ? "KO" : "EN";
  const key = currentLanguage === "ko" ? "switchToEnglish" : "switchToKorean";
  btn.setAttribute("aria-label", t(key));
  btn.setAttribute("title", t(key));
}

function applyLanguage(language) {
  currentLanguage = language === "ko" ? "ko" : "en";
  savePreference(LANGUAGE_PREFERENCE_KEY, currentLanguage);
  syncLanguageInUrl();
  updateUIText();
  if (!hasConversationHistory()) {
    clearChat();
  }
  renderReferencesList(currentReferences);
  updateGeneSelectionPreview();
}

function toggleLanguage() {
  applyLanguage(currentLanguage === "ko" ? "en" : "ko");
}

function syncThemeButtons() {
  const icon = currentTheme === "dark" ? "☀" : "☾";
  ["theme-toggle-top"].forEach((id) => {
    const btn = $(id);
    if (!btn) return;
    if (btn.querySelector(".theme-icon") && btn.querySelector(".theme-label")) {
      btn.querySelector(".theme-icon").textContent = icon;
      const key = currentTheme === "dark" ? "lightMode" : "darkMode";
      btn.querySelector(".theme-label").textContent = t(key);
      btn.setAttribute("aria-label", t(key));
      btn.setAttribute("title", t(key));
    } else if (btn.querySelector(".theme-icon")) {
      btn.querySelector(".theme-icon").textContent = icon;
      const key = currentTheme === "dark" ? "lightMode" : "darkMode";
      btn.setAttribute("aria-label", t(key));
      btn.setAttribute("title", t(key));
    } else {
      const key = currentTheme === "dark" ? "lightMode" : "darkMode";
      btn.textContent = t(key);
    }
  });

}

function applyTheme(theme) {
  rememberSelectedIndividual();
  currentTheme = theme === "dark" ? "dark" : "light";
  savePreference(THEME_PREFERENCE_KEY, currentTheme);
  document.body.classList.toggle("dark-theme", currentTheme === "dark");
  syncThemeButtons();
  rerenderPlotsForTheme();
  restoreSelectedIndividual();
}

function toggleTheme() {
  applyTheme(currentTheme === "dark" ? "light" : "dark");
}

function isDarkTheme() {
  return currentTheme === "dark";
}

function rerenderPlotsForTheme() {
  try {
    if (currentManhattanData && $("manhattan-plot")) {
      renderManhattanPlotly(currentManhattanData, "manhattan-plot");
      $("manhattan-plot").style.display = "block";
    }
    if (currentDensityData && $("density-plot")) {
      renderDensityPlotly(currentDensityData, "density-plot");
      $("density-plot").style.display = "block";
    }
    if (currentManhattanData && $("plot-overlay")?.classList.contains("is-open")) {
      renderExpandedManhattanPlot();
    }
  } catch (e) {
    console.warn("Plot theme rerender failed:", e);
  }
}

function escapeHtml(str) {
  return (str || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderManhattanPlotly(manhattan, containerId, options = {}) {
  const el = document.getElementById(containerId);
  if (!el) throw new Error(`Missing container #${containerId}`);
  const expanded = Boolean(options.expanded);

  const pts = manhattan?.points || [];
  const xs = pts.map(p => p.x);
  const ys = pts.map(p => p.variance);

  // hover fields
  const customdata = pts.map(p => [p.gene, p.chr, p.pos, p.variance]);

  const centers = manhattan?.chr_centers || [];
  const tickvals = centers.map(c => c.center);
  const ticktext = centers.map(c => String(c.chr));

  const trace = {
    type: "scattergl",
    mode: "markers",
    x: xs,
    y: ys,
    customdata,
    hovertemplate:
      "Gene: %{customdata[0]}<br>" +
      "Chromosome: %{customdata[1]}<br>" +
      "Position: %{customdata[2]}<br>" +
      "Variance: %{customdata[3]:.3e}" +
      "<extra></extra>",
    marker: {
      size: expanded ? 8 : 6,
      opacity: 0.85,
      color: pts.map(p => p.chr % 2 === 0 ? "#2c3e50" : "#95a5a6")
    }
  };

  const layout = {
    paper_bgcolor: isDarkTheme() ? "#111923" : "#ffffff",
    plot_bgcolor: isDarkTheme() ? "#111923" : "#ffffff",
    font: { color: isDarkTheme() ? "#dce6f2" : "#2c3e50" },
    margin: expanded
      ? { l: 76, r: 32, t: 36, b: 88 }
      : { l: 42, r: 14, t: 18, b: 40 },
    xaxis: {
      title: {
        text: "Chromosome",
        font: { size: expanded ? 14 : 12}
      },
      automargin: true,
      tickmode: "array",
      tickvals,
      ticktext,
      tickfont: { size: expanded ? 12 : 10},
      gridcolor: isDarkTheme() ? "#2b3b4f" : "#e5e7eb",
      showgrid: false,
      zeroline: false
    },
    yaxis: {
      title: {
        text: manhattan?.y_label || "Variance",
        font: { size: expanded ? 14 : 12 }
      },
      automargin: true,
      tickfont: { size: expanded ? 12 : 10 },
      gridcolor: isDarkTheme() ? "#2b3b4f" : "#e5e7eb",
      zeroline: true
    },
    hovermode: "closest"
  };

  const config = {
    displaylogo: false,
    displayModeBar: expanded,
    responsive: true,
    scrollZoom: expanded,
  };

  // Make sure Plotly is present
  if (!window.Plotly) throw new Error("Plotly.js not loaded. Did you add the CDN script tag?");
  window.Plotly.newPlot(el, [trace], layout, config);
}

function renderDensityPlotly(density, containerId) {
  const el = document.getElementById(containerId);
  if (!el) throw new Error(`Missing container #${containerId}`);
  if (!window.Plotly) throw new Error("Plotly.js not loaded.");

  const dx = density?.density?.x || [];
  const dy = density?.density?.y || [];
  const prsValue = Number(density?.prs_value);
  const cohort = (density?.cohort_prs || []).map(Number).filter(Number.isFinite);

  if (!dx.length || !dy.length || !Number.isFinite(prsValue) || !cohort.length) {
    throw new Error("Density JSON missing required fields (density.x/y, prs_value, cohort_prs).");
  }

  // Sort once for fast percentile lookup
  cohort.sort((a, b) => a - b);

  function percentileAt(x) {
    // upper_bound: count of values <= x
    let lo = 0, hi = cohort.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (cohort[mid] <= x) lo = mid + 1;
      else hi = mid;
    }
    return lo / cohort.length;
  }

  // Trace 1: density curve
  const traceDensity = {
    type: "scatter",
    mode: "lines",
    x: dx,
    y: dy,
    showlegend: false,
    line: { color: "#1f77d0", width: 2.5 },
    hoverinfo: "skip",
  };

  // Trace 2: invisible points to ensure hover works smoothly across the curve
  // (This improves hover responsiveness vs pure lines in some cases.)
  const traceHover = {
    type: "scatter",
    mode: "markers",
    x: dx,
    y: dy,
    marker: { size: 14, opacity: 0 },
    showlegend: false,
    hoverinfo: "none",
    customdata: dx.map(x => percentileAt(x) * 100)
  };

  // Initial shapes: fixed red PRS line + (optional) cursor line
  const shapes = [
    {
      type: "line",
      x0: prsValue, x1: prsValue,
      y0: 0, y1: 1,
      xref: "x",
      yref: "paper",
      line: { width: 2, color: "red" }
    },
    {
      type: "line",
      x0: prsValue, x1: prsValue, // will update on hover
      y0: 0, y1: 1,
      xref: "x",
      yref: "paper",
      line: { width: 1, color: "#9ca3af", dash: "dot" }
    }
  ];

  // Annotation for live percentile readout
  const annotations = [
    {
      x: 0.98,
      y: 0.98,
      xref: "paper",
      yref: "paper",
      xanchor: "right",
      yanchor: "top",
      align: "left",
  
      text:
        `<b>PRS:</b> ${prsValue.toFixed(3)}<br>` +
        `<b>Pctl.:</b> ${(density.percentile * 100).toFixed(2)}%`,
  
      showarrow: false,
  
      font: {
        size: 11,
        color: isDarkTheme() ? "#dce6f2" : "#374151"
      },
  
      bgcolor: isDarkTheme() ? "rgba(17,25,35,0.92)" : "rgba(249,250,251,0.95)",
      bordercolor: isDarkTheme() ? "#314255" : "#e5e7eb",
      borderwidth: 1,
      borderpad: 6
    }
  ];

  const layout = {
    paper_bgcolor: isDarkTheme() ? "#111923" : "#ffffff",
    plot_bgcolor: isDarkTheme() ? "#111923" : "#ffffff",
    font: { color: isDarkTheme() ? "#dce6f2" : "#2c3e50" },
    margin: { l: 44, r: 16, t: 18, b: 40 },
    xaxis: {
      title: { text: density?.x_label || "PRS", font: { size: 12 } },
      automargin: true,
      tickfont: { size: 10 },
      gridcolor: isDarkTheme() ? "#2b3b4f" : "#e5e7eb",
      showgrid: false,
      zeroline: false
    },
    yaxis: {
      title: { text: density?.y_label || "Density", font: { size: 12 } },
      automargin: true,
      tickfont: { size: 10 },
      gridcolor: isDarkTheme() ? "#2b3b4f" : "#e5e7eb",
      showgrid: true
    },
    hoverdistance: 40,
    hovermode: "closest",
    shapes,
    annotations
  };

  const config = { displaylogo: false, displayModeBar: false, responsive: true };

  Plotly.newPlot(el, [traceDensity, traceHover], layout, config);

  // Hover interaction:
  // - move cursor line to hovered x
  // - compute percentile and update annotation text
  // - bold the red line if cursor is close to prsValue
  el.on("plotly_hover", (ev) => {
    const x = ev?.points?.[0]?.x;
    if (!Number.isFinite(x)) return;

    const pct = percentileAt(x) * 100;
    const near = Math.abs(x - prsValue) <= 0.03; // adjust threshold to taste

    const newShapes = [...shapes];
    // cursor line is shapes[1]
    newShapes[1] = {
      ...newShapes[1],
      x0: x,
      x1: x
    };
    // red line is shapes[0]
    newShapes[0] = {
      ...newShapes[0],
      line: { ...newShapes[0].line, width: near ? 4 : 2 }
    };

    const newAnnotations = [{
      ...annotations[0],
      text:
        `<b>PRS:</b> ${Number(x).toFixed(3)}<br>` +
        `<b>Pctl.:</b> ${Number(pct).toFixed(2)}%`
    }];
    
    Plotly.relayout(el, { shapes: newShapes, annotations: newAnnotations });
  });

  el.on("plotly_unhover", () => {
    const basePct = Number(density?.percentile) * 100;
    const resetShapes = [...shapes];
    resetShapes[1] = {
      ...resetShapes[1],
      x0: prsValue,
      x1: prsValue
    };
  
    const resetAnnotations = [{
      ...annotations[0],
      text:
        `<b>PRS:</b> ${prsValue.toFixed(3)}<br>` +
        `<b>Pctl.:</b> ${basePct.toFixed(2)}%`
    }];
  
    Plotly.relayout(el, { shapes: resetShapes, annotations: resetAnnotations });
  });
}

async function loadAppInfo() {
  try {
    const res = await fetch("/api/info");
    if (res.ok) {
      const data = await res.json();
      // Store the resolved OpenRouter or local model name globally.
      if (data.model) {
        activeModelName = data.model;
      }
      syncEvaluationAvailability(data.evaluation_enabled === true);
    }
  } catch (e) {
    console.warn("Failed to load model info:", e);
    syncEvaluationAvailability(false);
  }
}

async function loadPhenotypeConfig() {
  try {
    const res = await fetch("/api/phenotype_config");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    phenotypeLabelsKo = data?.ko_labels || {};
  } catch (e) {
    console.warn("Failed to load phenotype config:", e);
    phenotypeLabelsKo = {};
  }
}

async function loadDiseaseRegistry() {
  try {
    const res = await fetch("/api/diseases");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = Array.isArray(data.diseases) ? data.diseases : [];
    diseaseRegistry = Object.fromEntries(items.map((item) => [item.slug, item]));
  } catch (e) {
    console.warn("Failed to load disease registry:", e);
    diseaseRegistry = {};
  }
  applyDiseaseMetadataToUI();
}

function hasConversationHistory() {
  return Boolean($("chat")?.querySelector(".msg-row"));
}

function resetReferenceViewer() {
  const panel = $("paper-body");
  if (panel) {
    panel.innerHTML = `<div class="placeholder" data-i18n="noPaperYet">${t("noPaperYet")}</div>`;
  }
  setStatus($("paper-status"), "");
}

function resetVisualizations() {
  const manhattanPlot = $("manhattan-plot");
  const densityPlot = $("density-plot");
  currentManhattanData = null;
  currentDensityData = null;
  closePlotOverlay();

  if (window.Plotly) {
    if (manhattanPlot) {
      window.Plotly.purge(manhattanPlot);
    }
    if (densityPlot) {
      window.Plotly.purge(densityPlot);
    }
  }

  if (manhattanPlot) manhattanPlot.style.display = "none";
  if (densityPlot) densityPlot.style.display = "none";

  syncManhattanPopoutButton();
  setStatus($("viz-status"), "");
}

function resetConversationState() {
  clearChat();
  currentReferences = [];
  renderReferencesList([]);
  resetReferenceViewer();
  activeSessionId = null;
  activeSummaryIndividualId = null;
  updateExportButtons();
}

function resetDashboardForIndividualChange() {
  resetConversationState();
  resetVisualizations();
}

function getReferenceIdentity(ref) {
  if (ref?.paperId) return `paper:${ref.paperId}`;
  if (ref?.url) return `url:${ref.url}`;
  return `meta:${ref?.title || ""}|${ref?.gene || ""}|${ref?.source || ""}`;
}

function mergeReferences(existingRefs, incomingRefs) {
  const merged = Array.isArray(existingRefs) ? [...existingRefs] : [];
  const seen = new Set(merged.map(getReferenceIdentity));

  for (const ref of Array.isArray(incomingRefs) ? incomingRefs : []) {
    const key = getReferenceIdentity(ref);
    if (seen.has(key)) continue;
    merged.push(ref);
    seen.add(key);
  }

  return merged.sort((a, b) => Number(a?.n || 0) - Number(b?.n || 0));
}

function highlightReferenceByNumber(refNumber) {
  const refsBody = $("refs-body");
  if (!refsBody || !refNumber) return;

  document.querySelectorAll(".ref-item").forEach((el) => {
    el.classList.remove("active");
  });

  const target = refsBody.querySelector(`.ref-item[data-ref-number="${refNumber}"]`);
  if (!target) return;

  target.classList.add("active");
  target.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function injectCitationLinks(containerEl) {
  if (!containerEl) return;

  const walker = document.createTreeWalker(containerEl, NodeFilter.SHOW_TEXT);
  const textNodes = [];

  while (walker.nextNode()) {
    const node = walker.currentNode;
    const parentTag = node.parentElement?.tagName;
    if (!node.nodeValue || !/\[\d+\]/.test(node.nodeValue)) continue;
    if (parentTag === "A" || parentTag === "BUTTON" || parentTag === "CODE" || parentTag === "PRE") continue;
    textNodes.push(node);
  }

  textNodes.forEach((node) => {
    const text = node.nodeValue || "";
    const parts = text.split(/(\[\d+\])/g);
    if (parts.length <= 1) return;

    const fragment = document.createDocumentFragment();
    for (const part of parts) {
      const match = part.match(/^\[(\d+)\]$/);
      if (!match) {
        fragment.appendChild(document.createTextNode(part));
        continue;
      }

      const citation = document.createElement("a");
      citation.href = "#";
      citation.className = "chat-ref-link";
      citation.dataset.refNumber = match[1];
      citation.textContent = part;
      fragment.appendChild(citation);
    }

    node.parentNode?.replaceChild(fragment, node);
  });
}

function injectPdfDownloadLinks(containerEl) {
  if (!containerEl) return;

  const phrases = [
    "downloadable PDF report",
    "다운로드 가능한 PDF 보고서",
    "상세 PDF 보고서",
  ];
  const pattern = new RegExp(`(${phrases.map((phrase) => phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "g");
  const walker = document.createTreeWalker(containerEl, NodeFilter.SHOW_TEXT);
  const textNodes = [];

  while (walker.nextNode()) {
    const node = walker.currentNode;
    const parentTag = node.parentElement?.tagName;
    if (!node.nodeValue || !pattern.test(node.nodeValue)) continue;
    pattern.lastIndex = 0;
    if (parentTag === "A" || parentTag === "BUTTON" || parentTag === "CODE" || parentTag === "PRE") continue;
    textNodes.push(node);
  }

  textNodes.forEach((node) => {
    const text = node.nodeValue || "";
    if (!pattern.test(text)) return;
    pattern.lastIndex = 0;

    const fragment = document.createDocumentFragment();
    let lastIndex = 0;

    text.replace(pattern, (match, _group, offset) => {
      if (offset > lastIndex) {
        fragment.appendChild(document.createTextNode(text.slice(lastIndex, offset)));
      }
      const link = document.createElement("a");
      link.href = "#";
      link.className = "chat-pdf-link";
      link.dataset.action = "download-pdf-report";
      link.textContent = match;
      fragment.appendChild(link);
      lastIndex = offset + match.length;
      return match;
    });

    if (lastIndex < text.length) {
      fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
    }

    node.parentNode?.replaceChild(fragment, node);
  });
}

function injectOpenTargetsCitations(containerEl) {
  if (!containerEl) return;

  const walker = document.createTreeWalker(containerEl, NodeFilter.SHOW_TEXT);
  const textNodes = [];

  while (walker.nextNode()) {
    const node = walker.currentNode;
    const parentTag = node.parentElement?.tagName;
    if (!node.nodeValue || !/\[OT:\s*[^\]]+\]/.test(node.nodeValue)) continue;
    if (parentTag === "A" || parentTag === "BUTTON" || parentTag === "CODE" || parentTag === "PRE") continue;
    textNodes.push(node);
  }

  textNodes.forEach((node) => {
    const text = node.nodeValue || "";
    const parts = text.split(/(\[OT:\s*[^\]]+\])/g);
    if (parts.length <= 1) return;

    const fragment = document.createDocumentFragment();
    for (const part of parts) {
      const match = part.match(/^\[OT:\s*[^\]]+\]$/);
      if (!match) {
        fragment.appendChild(document.createTextNode(part));
        continue;
      }

      const citation = document.createElement("span");
      citation.className = "ot-ref";
      citation.textContent = part;
      fragment.appendChild(citation);
    }

    node.parentNode?.replaceChild(fragment, node);
  });
}

function renderMath(containerEl) {
  if (!containerEl || typeof window.renderMathInElement !== "function") return;
  try {
    window.renderMathInElement(containerEl, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
      ],
      throwOnError: false,
      strict: "ignore",
      ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code"],
    });
  } catch (_) {
    // Leave the original text visible if KaTeX cannot render it.
  }
}

function normalizeMathMarkup(text) {
  let normalized = String(text || "");

  // Repair common XPRS symbols emitted with Markdown-style escaped underscores.
  // In LaTeX, `\_` means a literal underscore; named subscripts need braces and
  // roman text instead. This also repairs previously saved chat answers.
  normalized = normalized
    .replace(/\bCS\\?_\{gene\\?_j\}/gi, "CS_{\\mathrm{gene},j}")
    .replace(/\bCS\\?_\{gene\}/gi, "CS_{\\mathrm{gene}}")
    .replace(/\bA\\?_\{gene\\?_j\}/gi, "A_{\\mathrm{gene},j}")
    .replace(/\bA\\?_\{gene\}/gi, "A_{\\mathrm{gene}}")
    .replace(/\bCS\\?_\{SNP\\?_i\}/gi, "CS_{\\mathrm{SNP},i}")
    .replace(/\bCS\\?_\{SNP\}/gi, "CS_{\\mathrm{SNP}}");

  // Repair malformed inline-math delimiters that sometimes come back as
  // escaped opening/closing dollars, e.g. "\$M$" or "\$G_{i}\$".
  normalized = normalized.replace(/\\\$(.+?)\\\$/gs, (_match, expr) => {
    const trimmed = String(expr || "").trim();
    return trimmed ? `$${trimmed}$` : _match;
  });
  normalized = normalized.replace(/\\\$(.+?)\$/gs, (_match, expr) => {
    const trimmed = String(expr || "").trim();
    return trimmed ? `$${trimmed}$` : _match;
  });
  normalized = normalized.replace(/\$(.+?)\\\$/gs, (_match, expr) => {
    const trimmed = String(expr || "").trim();
    return trimmed ? `$${trimmed}$` : _match;
  });

  // Convert bracketed pseudo-display math like:
  // [ \text{mean}(...) ]
  // into proper KaTeX display delimiters, while avoiding citations like [1].
  normalized = normalized.replace(/\[\s*([^\[\]]*(?:\\[A-Za-z]+|[_^])[^\[\]]*)\s*\]/gs, (_, expr) => {
    const trimmed = String(expr || "").trim();
    if (!trimmed) return _;
    if (/^\d+(?:\s*,\s*\d+)*$/.test(trimmed)) return _;
    if (/^OT:\s*/.test(trimmed)) return _;
    return `\n\n$$${trimmed}$$\n\n`;
  });

  // If the model emits a standalone LaTeX-looking equation line without delimiters,
  // wrap it so KaTeX can render it.
  normalized = normalized.replace(
    /(^|\n)([ \t]*)([A-Za-z\\][^\n]*?(?:\\[A-Za-z]+|[_^]|\\cdot|=)[^\n]*)(?=\n|$)/g,
    (match, prefix, indent, line) => {
      const trimmed = String(line || "").trim();
      if (!trimmed) return match;
      if (trimmed.startsWith("$")) return match;
      if (trimmed.startsWith("- ") || trimmed.startsWith("* ") || /^\d+\.\s/.test(trimmed)) return match;
      if (!(/[=_^\\]/.test(trimmed))) return match;
      if (!(/[A-Za-z]/.test(trimmed))) return match;
      return `${prefix}${indent}$$${trimmed}$$`;
    }
  );

  return normalized;
}

function addMessage(role, text, options = {}) {
  const chat = $("chat");

  // Remove welcome block on first message
  const welcome = chat?.querySelector?.(".welcome");
  if (welcome) welcome.remove();

  const row = document.createElement("div");
  row.className = `msg-row ${role === "user" ? "user-row" : "bot-row"}`;

  const bubble = document.createElement("div");
  bubble.className = `msg-bubble ${role}`;

  if (role === "bot") {
    const modelName = String(options.modelName || activeModelName || "").trim();
    const shouldShowModel = options.showModel !== false && modelName && modelName.toLowerCase() !== "ai";
    const individualLabel = options.individualId
      ? `<div class="msg-individual-id">Individual: ${escapeHtml(options.individualId)}</div>`
      : "";
    const modelLabel = !shouldShowModel
      ? ""
      : `<div class="msg-model-label">Generated with ${escapeHtml(modelName)}</div>`;
    const normalizedText = normalizeMathMarkup(text || "");
    const rendered = window.marked ? window.marked.parse(normalizedText) : normalizedText;
    bubble.innerHTML = `${individualLabel}${rendered}${modelLabel}`;
    renderMath(bubble);
    injectOpenTargetsCitations(bubble);
    injectCitationLinks(bubble);
    injectPdfDownloadLinks(bubble);
    injectPaperIds(bubble);
  } else {
    bubble.innerHTML = escapeHtml(text || "");
  }

  row.appendChild(bubble);
  chat.appendChild(row);
  chat.scrollTop = chat.scrollHeight;
}

function appendLoadingBubbleLog(message) {
  if (!activeLoadingLogEl || !message) return;
  stopLoadingEllipsisAnimation();
  const line = document.createElement("div");
  line.className = "backend-log-line";
  line.textContent = message;
  activeLoadingLogEl.appendChild(line);
  activeLoadingLogEl.scrollTop = activeLoadingLogEl.scrollHeight;
  if (shouldAnimateBackendLogLine(message)) {
    activeLoadingAnimatedLineEl = line;
    startLoadingEllipsisAnimation();
  }
}

function shouldAnimateBackendLogLine(message) {
  return !/:\s*\d+(?:\.\d+)?(?:ms|s)\b/.test(message || "");
}

function startLoadingEllipsisAnimation() {
  if (!activeLoadingAnimatedLineEl) return;
  activeLoadingAnimatedBaseText = activeLoadingAnimatedLineEl.textContent || "";
  let dots = 0;
  activeLoadingAnimationTimer = window.setInterval(() => {
    if (!activeLoadingAnimatedLineEl) return;
    dots = (dots + 1) % 4;
    activeLoadingAnimatedLineEl.textContent = `${activeLoadingAnimatedBaseText}${".".repeat(dots)}`;
  }, 1000);
}

function stopLoadingEllipsisAnimation() {
  if (activeLoadingAnimationTimer) {
    clearInterval(activeLoadingAnimationTimer);
    activeLoadingAnimationTimer = null;
  }
  if (activeLoadingAnimatedLineEl) {
    activeLoadingAnimatedLineEl.textContent = activeLoadingAnimatedBaseText;
  }
  activeLoadingAnimatedLineEl = null;
  activeLoadingAnimatedBaseText = "";
}

function captureLoadingBubbleLogHtml() {
  return activeLoadingLogEl ? activeLoadingLogEl.innerHTML : "";
}

function buildBackendLogBoxHtml(logHtml, collapsed = true) {
  if (!logHtml || !logHtml.trim()) return "";
  const expanded = !collapsed;
  const arrow = expanded ? "▼" : "▶";
  return `
    <button type="button" class="backend-log-toggle" aria-expanded="${expanded ? "true" : "false"}">
      <span class="backend-log-toggle__arrow" aria-hidden="true">${arrow}</span>
      <span>Backend Processes</span>
    </button>
    <div class="backend-log-box__body${collapsed ? " is-collapsed" : ""}">${logHtml}</div>
  `;
}

function appendBackendLogBox(logHtml) {
  if (!logHtml || !logHtml.trim()) return;
  const chat = $("chat");
  if (!chat) return;

  const row = document.createElement("div");
  row.className = "msg-row bot-row";

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble bot backend-log-bubble";
  bubble.innerHTML = buildBackendLogBoxHtml(logHtml, true);
  const toggle = bubble.querySelector(".backend-log-toggle");
  const body = bubble.querySelector(".backend-log-box__body");
  toggle?.addEventListener("click", () => {
    const collapsed = body?.classList.toggle("is-collapsed");
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    const arrow = toggle.querySelector(".backend-log-toggle__arrow");
    if (arrow) arrow.textContent = collapsed ? "▶" : "▼";
  });

  row.appendChild(bubble);
  chat.appendChild(row);
  chat.scrollTop = chat.scrollHeight;
}

function showLoadingBubble() {
  const chat = $("chat");
  if (!chat) return;
  const welcome = chat.querySelector(".welcome");
  if (welcome) welcome.remove();
  removeLoadingBubble();

  const row = document.createElement("div");
  row.className = "msg-row bot-row";
  row.id = "summary-loading-row";

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble bot backend-log-bubble backend-log-bubble--live";
  bubble.innerHTML = `
    <div class="backend-log-live__body"></div>
  `;

  row.appendChild(bubble);
  chat.appendChild(row);
  chat.scrollTop = chat.scrollHeight;
  activeLoadingBubble = row;
  activeLoadingLogEl = bubble.querySelector(".backend-log-live__body");
}

function removeLoadingBubble() {
  stopLoadingEllipsisAnimation();
  if (activeLoadingBubble?.parentNode) {
    activeLoadingBubble.parentNode.removeChild(activeLoadingBubble);
  }
  activeLoadingBubble = null;
  activeLoadingLogEl = null;
}

function bustCache(url) {
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}t=${Date.now()}`;
}

async function postJSON(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${txt}`);
  }
  return res.json();
}

function updateExportButtons() {
  const enabled = Boolean(activeSessionId && activeSummaryIndividualId);
  const menuBtn = $("export-menu-btn");
  if (menuBtn) {
    menuBtn.disabled = !enabled;
    if (!enabled) {
      closeExportMenu();
    }
  }
  ["download-pdf-btn", "download-chat-md-btn", "download-chat-json-btn"].forEach((id) => {
    const btn = $(id);
    if (btn) btn.disabled = !enabled;
  });
}

function openExportMenu() {
  const menu = $("export-menu");
  const btn = $("export-menu-btn");
  if (!menu || !btn || btn.disabled) return;
  menu.hidden = false;
  btn.setAttribute("aria-expanded", "true");
}

function closeExportMenu() {
  const menu = $("export-menu");
  const btn = $("export-menu-btn");
  if (!menu || !btn) return;
  menu.hidden = true;
  btn.setAttribute("aria-expanded", "false");
}

function toggleExportMenu() {
  const menu = $("export-menu");
  if (!menu || menu.hidden) {
    openExportMenu();
    return;
  }
  closeExportMenu();
}

async function loadModels() {
  try {
    const res = await fetch("/api/models");
    if (!res.ok) return;
    availableModels = await res.json();
    if (!selectedGenerationModel) {
      selectedGenerationModel = availableModels.default_generation || null;
    }
    populateGenerationModelSelect();
    // The selected option is the source of truth for requests and response labels.
    if (selectedGenerationModel) setActiveModelDisplay(selectedGenerationModel);
  } catch (e) {
    console.warn("Failed to load models:", e);
  }
}

function setActiveModelDisplay(modelId) {
  activeModelName = modelId;
}

function populateGenerationModelSelect() {
  const sel = $("generation-model-select");
  if (!sel || !availableModels) return;
  sel.innerHTML = "";
  (availableModels.generation || []).forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = m.label || m.id;
    if (m.id === selectedGenerationModel) opt.selected = true;
    sel.appendChild(opt);
  });
  sel.onchange = () => {
    selectedGenerationModel = sel.value;
    setActiveModelDisplay(sel.value);
  };
}

function getFilenameFromResponse(response, fallback) {
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  return match?.[1] || fallback;
}

function triggerBlobDownload(blob, filename) {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

async function fetchDownload(url, options = {}, fallbackFilename = "download.bin") {
  const res = await fetch(url, options);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${txt}`);
  }
  const blob = await res.blob();
  return {
    blob,
    filename: getFilenameFromResponse(res, fallbackFilename),
  };
}

async function capturePlotImage(containerId) {
  const el = $(containerId);
  if (!el || el.style.display === "none" || !window.Plotly?.toImage) return null;
  try {
    const width = Math.max(el.clientWidth || 900, 900);
    const height = Math.max((el.clientHeight || 360) + 80, 440);
    return await window.Plotly.toImage(el, {
      format: "png",
      width,
      height,
      scale: 2,
    });
  } catch (err) {
    console.warn(`Failed to capture plot image for ${containerId}:`, err);
    return null;
  }
}

async function downloadPdfReport() {
  if (!activeSessionId || !activeSummaryIndividualId) {
    setStatus($("chat-status"), t("exportUnavailable"));
    return;
  }

  setStatus($("chat-status"), t("exportPdfLoading"));
  try {
    const [densityImage, manhattanImage] = await Promise.all([
      capturePlotImage("density-plot"),
      capturePlotImage("manhattan-plot"),
    ]);
    const { blob, filename } = await fetchDownload("/api/report/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: activeSessionId,
        individual_id: activeSummaryIndividualId,
        disease: getActiveDiseaseSlug(),
        language: currentLanguage,
        density_image_data: densityImage,
        manhattan_image_data: manhattanImage,
      }),
    }, `xprs_report_${activeSummaryIndividualId}.pdf`);
    triggerBlobDownload(blob, filename);
  } finally {
    closeExportMenu();
    setStatus($("chat-status"), "");
  }
}

async function downloadChatExport(kind) {
  if (!activeSessionId || !activeSummaryIndividualId) {
    setStatus($("chat-status"), t("exportUnavailable"));
    return;
  }

  const suffix = kind === "json" ? "json" : "md";
  setStatus($("chat-status"), t("exportChatLoading"));
  try {
    const { blob, filename } = await fetchDownload(
      `/api/session/${encodeURIComponent(activeSessionId)}/chat.${suffix}`,
      {},
      `xprs_chat_${activeSummaryIndividualId}.${suffix}`
    );
    triggerBlobDownload(blob, filename);
  } finally {
    closeExportMenu();
    setStatus($("chat-status"), "");
  }
}

async function runTaskStream(startUrl, payload, { onProgress } = {}) {
  const { task_id: taskId } = await postJSON(startUrl, payload);
  if (!taskId) throw new Error("Task start failed: missing task_id");

  return await new Promise((resolve, reject) => {
    const es = new EventSource(`/api/tasks/${encodeURIComponent(taskId)}/events`);
    let settled = false;

    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      es.close();
      fn(value);
    };

    es.addEventListener("progress", (event) => {
      try {
        const data = JSON.parse(event.data || "{}");
        if (typeof data.message === "string" && onProgress) {
          onProgress(data.message);
        }
      } catch (_) {}
    });

    es.addEventListener("complete", (event) => {
      try {
        finish(resolve, JSON.parse(event.data || "{}"));
      } catch (err) {
        finish(reject, err);
      }
    });

    es.addEventListener("failed", (event) => {
      try {
        const data = JSON.parse(event.data || "{}");
        finish(reject, new Error(data.message || "Task failed"));
      } catch (_) {
        finish(reject, new Error("Task stream failed"));
      }
    });

    es.onerror = () => {
      if (!settled) {
        finish(reject, new Error("Task stream connection lost"));
      }
    };
  });
}

function setImage(imgEl, placeholderEl, metaEl, url, metaText) {
  // NEW: guard for removed elements
  if (!imgEl || !placeholderEl) {
    // still allow meta updates if present
    setStatus(metaEl, metaText || "—");
    return;
  }

  if (!url) {
    imgEl.style.display = "none";
    placeholderEl.style.display = "block";
    setStatus(metaEl, "—");
    return;
  }
  placeholderEl.style.display = "none";
  imgEl.style.display = "block";
  imgEl.src = bustCache(url);
  setStatus(metaEl, metaText || "updated");
}

function setLoading(isLoading) {
  const headerSummaryBtn = $("header-generate-btn");
  const sendBtn = $("send-btn");
  const input = $("user-input");

  if (headerSummaryBtn) {
    headerSummaryBtn.disabled = isLoading;
    headerSummaryBtn.innerHTML = isLoading
      ? `<span class="loading-spinner"></span>${t("summaryLoading")}`
      : t("generateSummary");
  }
  if (sendBtn) sendBtn.disabled = isLoading;
  if (input) input.disabled = isLoading;
}

function clearChat() {
  const chat = $("chat");
  if (!chat) return;
  chat.innerHTML = "";
  setStatus($("chat-status"), "");
}

function renderReferencesList(refs) {
  const el = $("refs-body");
  const refsStatus = $("refs-status");
  if (!el) return;

  const renderPhenotypeChips = (rawPhenotype) => {
    const values = String(rawPhenotype || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    return values
      .map((value) => `<span class="ref-phenotype">${escapeHtml(localizePhenotypeLabel(value))}</span>`)
      .join("");
  };

  if (!Array.isArray(refs) || refs.length === 0) {
    el.innerHTML = `<div class="placeholder">${t("noReferencesYet")}</div>`;
    if (refsStatus) refsStatus.textContent = "";
    return;
  }

  if (refsStatus) {
    refsStatus.textContent = `${refs.length} source${refs.length === 1 ? "" : "s"}`;
  }

  el.innerHTML = refs.map((r) => {
    const n = r.n ?? "";
    const title = escapeHtml(r.title || "Untitled");
    const gene = escapeHtml(r.gene || "");
    const journal = escapeHtml(r.journal || "");
    const citationCount = Number.isFinite(Number(r.citationCount)) ? Number(r.citationCount) : null;
    const phenotypeChips = renderPhenotypeChips(r.phenotype);
    const publicationLine = (journal || citationCount !== null)
      ? `<span class="ref-publication-line">${
          journal ? `<span class="ref-detail ref-detail--journal">${journal}</span>` : ""
        }${
          citationCount !== null
            ? `<span class="ref-detail ref-detail--citations">${escapeHtml(t("citedCount")(citationCount))}</span>`
            : ""
        }</span>`
      : "";

    // Paper refs are clickable
    if (r.paperId) {
      return `
        <div class="ref-item" data-paper-id="${escapeHtml(r.paperId)}" data-ref-number="${n}">
          <a class="ref-link" href="#" data-paper-id="${escapeHtml(r.paperId)}" data-gene="${gene}" data-ref-number="${n}">
            <span class="ref-number">[${n}]</span> ${title}
          </a>
          <div class="ref-meta">
            ${gene ? `<span class="ref-gene">${gene}</span>` : ""}
            ${phenotypeChips}
            ${publicationLine}
          </div>
        </div>
      `;
    }

    // Non-paper refs remain non-clickable if they ever reappear.
    return `
      <div class="ref-item">
        <div class="ref-link ref-link--disabled">
          <span class="ref-number">[${n}]</span> ${title}
        </div>
        <div class="ref-meta">
          ${gene ? `<span class="ref-gene">${gene}</span>` : ""}
          ${phenotypeChips}
          ${publicationLine}
        </div>
      </div>
    `;
  }).join("");
}

function renderPaper(paper) {
  const panel = $("paper-body");
  if (!panel) return;
  const abstractText = escapeHtml((paper?.abstract || "No abstract available.").trim());

  // 1. Author Processing
  let authorDisplay = "";
  let fullAuthorList = "";

  if (Array.isArray(paper?.authors)) {
    const names = paper.authors.map((a) => a?.name).filter(Boolean);
    fullAuthorList = names.join(", ");
    if (names.length > 3) {
      authorDisplay = `${names[0]} et al.`;
    } else {
      authorDisplay = fullAuthorList;
    }
  } else {
    authorDisplay = paper?.authors || "";
    fullAuthorList = authorDisplay;
  }

  // 2. PMC Link Extraction
  let pmcLinkHtml = "";
  const disclaimer = paper?.openAccessPdf?.disclaimer || "";
  const pmcMatch = disclaimer.match(/https:\/\/pmc\.ncbi\.nlm\.nih\.gov\/articles\/PMC\d+/);
  
  if (pmcMatch) {
    const pmcUrl = pmcMatch[0];
    pmcLinkHtml = `
      <div class="paper-links__item">
        <a href="${pmcUrl}" target="_blank" rel="noreferrer" class="paper-link paper-link--pmc">
          <span>View on PubMed Central</span> ↗
        </a>
      </div>
    `;
  }

  // 3. Render
  const journalBits = [
    paper?.journal ? `<span class="paper-meta__journal">${escapeHtml(paper.journal)}</span>` : "",
    paper?.year ? `<span class="paper-meta__year">${paper.year}</span>` : "",
    Number.isFinite(Number(paper?.citationCount)) ? `<span class="paper-meta__citations">${escapeHtml(t("citedCount")(Number(paper.citationCount)))}</span>` : "",
  ].filter(Boolean).join('<span class="paper-meta__sep"> • </span>');

  panel.innerHTML = `
    <div class="paper-view">
      <div class="paper-view__header">
        <h3 class="paper-title">
          ${escapeHtml(paper?.title || "Untitled")}
        </h3>
        
        <p title="${escapeHtml(fullAuthorList)}" class="paper-meta">
          ${escapeHtml(authorDisplay)}
        </p>
        ${journalBits ? `<p class="paper-meta paper-meta--secondary">${journalBits}</p>` : ""}
      </div>

      <div class="paper-view__body">
        <hr class="paper-divider">
        <div class="paper-abstract-scroll">
          <div class="paper-abstract">${abstractText}</div>
        </div>
      </div>

      <div class="paper-view__footer">
        <div class="paper-links">
          ${
            paper?.url
              ? `<div class="paper-links__item">
                  <a href="${paper.url}" target="_blank" rel="noreferrer" class="paper-link">
                    <span>View on Semantic Scholar</span> ↗
                  </a>
                </div>`
              : ""
          }
          ${pmcLinkHtml}
        </div>
      </div>
    </div>
  `;
}

function injectPaperIds(containerEl) {
  if (!containerEl) return;

  const links = containerEl.querySelectorAll('a[href*="semanticscholar.org/paper/"]');
  links.forEach((a) => {
    const href = a.getAttribute("href") || "";
    const m = href.match(/semanticscholar\.org\/paper\/([0-9a-f]{40})/i);
    if (!m) return;

    a.dataset.paperId = m[1];
  });
}

// ----------------------------
// Load individual list
// ----------------------------
async function loadIndividuals() {
  setStatus($("individual-status"), t("loadingIndividuals"));
  const res = await fetch("/api/individuals");
  if (!res.ok) throw new Error(`Failed to load individuals: HTTP ${res.status}`);
  const data = await res.json();
  allIndividuals = Array.isArray(data.individuals) ? data.individuals : [];
  renderIndividualOptions(allIndividuals);
  setStatus($("individual-status"), t("loadedIndividuals")(allIndividuals.length));
}

function renderIndividualOptions(individuals) {
  const sel = $("individual-id");
  if (!sel) return;
  const preferredSelection = getSelectedIndividualId() || lastSelectedIndividualId || "";
  sel.innerHTML = "";
  individuals.forEach((pid) => {
    const opt = document.createElement("option");
    opt.value = pid;
    opt.textContent = pid;
    sel.appendChild(opt);
  });
  if (individuals.length > 0) {
    sel.value = individuals.includes(preferredSelection) ? preferredSelection : individuals[0];
    lastSelectedIndividualId = sel.value;
    syncIndividualSearchDisplay(sel.value);
  } else {
    lastSelectedIndividualId = null;
    syncIndividualSearchDisplay("");
  }
  updateGeneSelectionPreview();
}

function selectIndividualById(pid) {
  const sel = $("individual-id");
  if (!sel || !pid) return false;
  const exists = Array.from(sel.options).some((opt) => opt.value === pid);
  if (!exists) return false;
  sel.value = pid;
  lastSelectedIndividualId = pid;
  syncIndividualSearchDisplay(pid);
  updateGeneSelectionPreview();
  return true;
}

function filterIndividuals() {
  const term = ($("individual-search")?.value || "").trim().toLowerCase();
  const filtered = !term
    ? allIndividuals
    : allIndividuals.filter((pid) => pid.toLowerCase().includes(term));
  renderIndividualOptions(filtered);
  setStatus($("individual-status"), t("loadedIndividuals")(filtered.length));
}

// ----------------------------
// Plot loading
// ----------------------------
async function loadPlotsForIndividual(pid) {
  if (!pid) return null;
  setStatus($("viz-status"), "Loading interactive plots...");
  const payload = await postJSON("/api/plotdata", {
    individual_id: pid,
    disease: getActiveDiseaseSlug(),
  });

  try {
    const manPlot = $("manhattan-plot");
    if (manPlot) {
      currentManhattanData = payload.manhattan;
      manPlot.style.display = "block";
      renderManhattanPlotly(payload.manhattan, "manhattan-plot");
      syncManhattanPopoutButton();
      if ($("plot-overlay")?.classList.contains("is-open")) {
        renderExpandedManhattanPlot();
      }
    }
  } catch (e) {
    console.warn("Manhattan render failed:", e);
    const manPlot = $("manhattan-plot");
    if (manPlot) manPlot.style.display = "none";
    currentManhattanData = null;
    syncManhattanPopoutButton();
  }

  try {
    const denPlot = $("density-plot");
    if (denPlot) {
      currentDensityData = payload.density;
      denPlot.style.display = "block";
      renderDensityPlotly(payload.density, "density-plot");
    }
  } catch (e) {
    console.warn("Density render failed:", e);
    const denPlot = $("density-plot");
    if (denPlot) denPlot.style.display = "none";
    currentDensityData = null;
  }

  setStatus($("viz-status"), "");
  return payload;
}

// ----------------------------
// Individual selection
// ----------------------------
async function changeIndividual() {
  const pid = getSelectedIndividualId();
  if (!pid) {
    showLandingWarning();
    return;
  }

  const changed = pid !== currentIndividualId;
  commitIndividualSelection(pid);
  clearLandingWarning();
  closeLandingModal(true);
  if (!changed) return;

  resetDashboardForIndividualChange();
  try {
    await loadPlotsForIndividual(pid);
  } catch (err) {
    console.error(err);
    setStatus($("viz-status"), `Plots unavailable: ${err.message}`);
  }
}

// ----------------------------
// Summary generation
// ----------------------------
async function generateSummary() {
  const pid = currentIndividualId || getSelectedIndividualId();
  const geneCount = getSummaryGeneCount();
  const language = currentLanguage;
  if (!pid) return;

  commitIndividualSelection(pid);
  resetConversationState();
  currentLanguage = language;
  updateUIText();
  syncLanguageToggle();
  clearLandingWarning();
  closeLandingModal(true);
  showLoadingBubble();

  setLoading(true);
  setStatus($("chat-status"), "");

  try {
    const summary = await runTaskStream("/api/summary/start", {
      individual_id: pid,
      disease: getActiveDiseaseSlug(),
      gene_count: geneCount,
      language,
      model: selectedGenerationModel,
    }, {
      onProgress: (message) => {
        appendLoadingBubbleLog(message);
      },
    });
    
    activeSessionId = summary.session_id || null;
    activeSummaryIndividualId = pid;
    currentReferences = Array.isArray(summary.references) ? summary.references : [];
    lastSelectedIndividualId = pid;
    setCurrentIndividualLabel(pid);
    updateExportButtons();
    const backendLogHtml = captureLoadingBubbleLogHtml();
    removeLoadingBubble();
    appendBackendLogBox(backendLogHtml);
    
    addMessage("bot", summary.simple_summary || summary.summary || "(No summary returned)", {
      individualId: pid,
      modelName: selectedGenerationModel || activeModelName,
    });
    renderReferencesList(currentReferences);
    setStatus($("chat-status"), "");
  } catch (e) {
    const backendLogHtml = captureLoadingBubbleLogHtml();
    removeLoadingBubble();
    appendBackendLogBox(backendLogHtml);
    addMessage("bot", e.message || "Summary generation failed.", {
      individualId: pid,
      showModel: false,
    });
    setStatus($("chat-status"), "");
  } finally {
    setLoading(false);
  }
}
  

// ----------------------------
// Follow-up chat
// ----------------------------
async function sendFollowup() {
  const pid = currentIndividualId || getSelectedIndividualId();
  const q = ($("user-input").value || "").trim();
  if (!q) return;

  addMessage("user", q);
  $("user-input").value = "";

  $("send-btn").disabled = true;
  
  setStatus($("chat-status"), "");
  showLoadingBubble();

  try {
    const res = await runTaskStream("/api/chat/start", {
      individual_id: pid,
      disease: getActiveDiseaseSlug(),
      query: q,
      session_id: activeSessionId,
      language: currentLanguage,
      model: selectedGenerationModel,
    }, {
      onProgress: (message) => {
        appendLoadingBubbleLog(message);
      },
    });
    
    if (res.session_id) {
      activeSessionId = res.session_id;
    }
    if (!activeSummaryIndividualId) {
      activeSummaryIndividualId = pid;
    }
    updateExportButtons();
    if (Array.isArray(res.references)) {
      currentReferences = mergeReferences(currentReferences, res.references);
      renderReferencesList(currentReferences);
    }
    const backendLogHtml = captureLoadingBubbleLogHtml();
    removeLoadingBubble();
    appendBackendLogBox(backendLogHtml);
    addMessage("bot", res.answer || "(No answer returned)", {
      individualId: pid,
      modelName: selectedGenerationModel || activeModelName,
    });
  } catch (e) {
    console.error(e);
    const backendLogHtml = captureLoadingBubbleLogHtml();
    removeLoadingBubble();
    appendBackendLogBox(backendLogHtml);
    addMessage("bot", `⚠️ Error: ${e.message}`, { individualId: pid, showModel: false });
  } finally {
    $("send-btn").disabled = false;
    setStatus($("chat-status"), "");
  }
}


// ----------------------------
// Paper
// ----------------------------
async function loadPaperFromCache({ paperId, gene }) {
  const qs = new URLSearchParams({ paper_id: paperId });
  if (gene) qs.set("gene", gene);

  const res = await fetch(`/api/paper?${qs.toString()}`);
  if (!res.ok) throw new Error(`Paper lookup failed: HTTP ${res.status}`);
  return res.json();
}

function wireReferenceClicks() {
  const clickHandler = async (e) => {
    const citationLink = e.target?.closest?.("a.chat-ref-link[data-ref-number]");
    if (citationLink) {
      e.preventDefault();
      const refNumber = citationLink.getAttribute("data-ref-number");
      highlightReferenceByNumber(refNumber);
      return;
    }

    const pdfLink = e.target?.closest?.("a.chat-pdf-link[data-action='download-pdf-report']");
    if (pdfLink) {
      e.preventDefault();
      try {
        await downloadPdfReport();
      } catch (err) {
        console.error(err);
        setStatus($("chat-status"), `Error: ${err.message}`);
      }
      return;
    }

    const a = e.target?.closest?.("a[data-paper-id]");
    if (!a) return;

    e.preventDefault();

    const paperId = a.getAttribute("data-paper-id");
    const gene = a.getAttribute("data-gene") || "";
    const refNumber = a.getAttribute("data-ref-number") || "";
    if (!paperId) return;

    setStatus($("paper-status"), "Loading paper details...");

    try {
      const paper = await loadPaperFromCache({ paperId, gene });
      renderPaper(paper);
      if (refNumber) {
        highlightReferenceByNumber(refNumber);
      } else {
        document.querySelectorAll(".ref-item").forEach(el => {
          el.classList.remove("active");
        });
        
        const active = document.querySelector(`.ref-item[data-paper-id="${paperId}"]`);
        if (active) active.classList.add("active");
      }
      setStatus($("paper-status"), "");
    } catch (err) {
      console.error(err);
      setStatus($("paper-status"), `Failed to load paper: ${err.message}`);
    }
  };

  const chat = $("chat");
  if (chat) chat.addEventListener("click", clickHandler);

  const refsBody = $("refs-body");
  if (refsBody) refsBody.addEventListener("click", clickHandler);
}

// ----------------------------
// Events
// ----------------------------
window.addEventListener("DOMContentLoaded", async () => {
  const params = dashboardUrlParams();
  const initialIndividualId = params.get("individual_id")
    || readPreference(INDIVIDUAL_PREFERENCE_KEY, "");
  const requestedLanguage = params.get("language");
  currentLanguage = requestedLanguage === "ko" || requestedLanguage === "en"
    ? requestedLanguage
    : readPreference(LANGUAGE_PREFERENCE_KEY, "en");
  savePreference(LANGUAGE_PREFERENCE_KEY, currentLanguage);
  syncLanguageInUrl();
  currentDiseaseSlug = params.get("disease") || params.get("phenotype") || "breast_cancer";
  if (!initialIndividualId) {
    openLandingModal();
  }
  applyTheme(readPreference(THEME_PREFERENCE_KEY, "light"));
  updateUIText();
  installDashboardPlotResizeHandling();
  updateExportButtons();
  updateGeneCountControl();
  clearLandingWarning();
  await loadDiseaseRegistry();
  await loadPhenotypeConfig();
  await loadAppInfo();
  await loadModels();
  await loadIndividuals();
  if (initialIndividualId && selectIndividualById(initialIndividualId)) {
    commitIndividualSelection(initialIndividualId);
    closeLandingModal(true);
    resetDashboardForIndividualChange();
    setStatus($("chat-status"), "");
    try {
      await loadPlotsForIndividual(initialIndividualId);
    } catch (err) {
      console.error(err);
      setStatus($("viz-status"), `Plots unavailable: ${err.message}`);
    }
  } else {
    if (initialIndividualId) {
      openLandingModal();
    }
    setCurrentIndividualLabel(currentIndividualId);
  }
  wireReferenceClicks();
  $("landing-change-btn").addEventListener("click", changeIndividual);
  $("header-generate-btn")?.addEventListener("click", generateSummary);
  $("send-btn").addEventListener("click", sendFollowup);
  $("export-menu-btn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleExportMenu();
  });
  $("download-pdf-btn")?.addEventListener("click", async () => {
    try {
      await downloadPdfReport();
    } catch (err) {
      console.error(err);
      setStatus($("chat-status"), `Error: ${err.message}`);
    }
  });
  $("download-chat-md-btn")?.addEventListener("click", async () => {
    try {
      await downloadChatExport("md");
    } catch (err) {
      console.error(err);
      setStatus($("chat-status"), `Error: ${err.message}`);
    }
  });
  $("download-chat-json-btn")?.addEventListener("click", async () => {
    try {
      await downloadChatExport("json");
    } catch (err) {
      console.error(err);
      setStatus($("chat-status"), `Error: ${err.message}`);
    }
  });

  const individualSelect = $("individual-id");
  if (individualSelect) {
    lastSelectedIndividualId = individualSelect.value || null;
    individualSelect.addEventListener("change", () => {
      lastSelectedIndividualId = individualSelect.value || lastSelectedIndividualId;
      syncIndividualSearchDisplay(lastSelectedIndividualId);
      updateGeneSelectionPreview();
      closeIndividualDropdown();
    });
    individualSelect.addEventListener("input", () => {
      lastSelectedIndividualId = individualSelect.value || lastSelectedIndividualId;
      syncIndividualSearchDisplay(lastSelectedIndividualId);
      updateGeneSelectionPreview();
    });
    individualSelect.addEventListener("click", () => {
      lastSelectedIndividualId = individualSelect.value || lastSelectedIndividualId;
      syncIndividualSearchDisplay(lastSelectedIndividualId);
      updateGeneSelectionPreview();
    });
  }

  const individualSearch = $("individual-search");
  if (individualSearch) {
    individualSearch.addEventListener("focus", () => {
      individualSearch.select();
      openIndividualDropdown();
    });
    individualSearch.addEventListener("click", () => {
      individualSearch.select();
      openIndividualDropdown();
    });
    individualSearch.addEventListener("input", filterIndividuals);
  }

  const summaryGeneCount = $("summary-gene-count");
  if (summaryGeneCount) {
    summaryGeneCount.addEventListener("input", () => {
      setSummaryGeneCount(summaryGeneCount.value || "2");
    });
  }

  document.querySelectorAll("[data-language-option]").forEach((btn) => {
    btn.addEventListener("click", () => {
      applyLanguage(btn.dataset.languageOption || "en");
    });
  });

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
  $("landing-disclaimer-btn")?.addEventListener("click", toggleLandingDisclaimer);
  $("landing-cancel-btn")?.addEventListener("click", () => closeLandingModal());

  const individualSelectorBtn = $("individual-selector-btn");
  if (individualSelectorBtn) {
    individualSelectorBtn.addEventListener("click", () => {
      openLandingModal();
    });
  }

  const landingBackdrop = $("landing-backdrop");
  if (landingBackdrop) {
    landingBackdrop.addEventListener("click", () => {
      closeLandingModal();
    });
  }

  $("manhattan-popout-btn")?.addEventListener("click", () => {
    openPlotOverlay();
  });

  $("close-plot-overlay-btn")?.addEventListener("click", () => {
    closePlotOverlay();
  });

  $("plot-overlay-backdrop")?.addEventListener("click", () => {
    closePlotOverlay();
  });

  document.addEventListener("click", (e) => {
    const wrap = document.querySelector(".export-menu-wrap");
    if (!wrap) return;
    if (wrap.contains(e.target)) return;
    closeExportMenu();
  });

  document.addEventListener("click", (e) => {
    const picker = $("landing-picker");
    const overlay = $("landing-overlay");
    if (!picker || !overlay?.classList.contains("is-open")) return;
    if (picker.contains(e.target)) return;
    closeIndividualDropdown();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if ($("plot-overlay")?.classList.contains("is-open")) {
      closePlotOverlay();
      return;
    }
    if ($("landing-overlay")?.classList.contains("is-open")) {
      closeLandingModal();
    }
  });

  window.addEventListener("resize", () => {
    if ($("plot-overlay")?.classList.contains("is-open") && $("manhattan-plot-expanded") && window.Plotly) {
      window.Plotly.Plots.resize($("manhattan-plot-expanded"));
    }
  });

  $("user-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendFollowup();
    }
  });

  syncManhattanPopoutButton();
  syncPlotOverlayUI();
});
