const $ = (id) => document.getElementById(id);

const LANGUAGE_KEY = "xprs.language";
const THEME_KEY = "xprs.theme";
let currentLanguage = "en";
let currentTheme = "light";
let currentPayload = null;
let requestId = 0;

const DISEASES = [
  ["breast_cancer", "Breast Cancer", "유방암"],
  ["colorectal_cancer", "Colorectal Cancer", "대장암"],
  ["pancreatic_cancer", "Pancreatic Cancer", "췌장암"],
  ["prostate_cancer", "Prostate Cancer", "전립선암"],
  ["uterine_cancer", "Uterine Cancer", "자궁암"],
  ["thyroid_cancer", "Thyroid Cancer", "갑상선암"],
  ["gastric_cancer", "Gastric Cancer", "위암"],
  ["type2_diabetes", "Type 2 Diabetes", "제2형 당뇨병"],
  ["coronary_artery_disease", "Coronary Artery Disease", "관상동맥질환"],
  ["myocardial_infarction", "Myocardial Infarction", "심근경색"],
];

const TEXT = {
  en: {
    documentTitle: "K-PREDICT Cohort Analysis",
    sectionLabel: "K-PREDICT · Population view",
    pageTitle: "Cohort Analysis",
    overview: "Disease overview",
    about: "About XPRS",
    prsDefinitionLabel: "PRS percentile",
    prsDefinition: " summarizes common-variant signal relative to applicable individuals in this cohort.",
    alertDefinitionLabel: "Panel alert",
    alertDefinition: " is a supplied finding that may act with one copy and was designated for prominent review.",
    carrierDefinitionLabel: "Carrier only",
    carrierDefinition: " is a supplied recessive heterozygous finding and is not classified as an alert.",
    introBoundary: "The comparison is descriptive. It does not combine the two evidence types, establish causation, or provide a diagnosis.",
    panelSourceAnswer: "The supplied pipeline mapped pathogenic or likely pathogenic findings to diseases by gene membership in Genomics England PanelApp GREEN panels. PanelApp and ClinGen modes of inheritance were then used to classify each finding as an alert or carrier. The portal preserves those supplied assignments and does not infer them from ClinVar condition text.",
    cardiacPanelCaveat: " PanelApp has no dedicated coronary artery disease or myocardial infarction panel, so the supplied pipeline uses the Familial hypercholesterolaemia panel as the closest monogenic analogue; these two diseases therefore share the same rare-variant gene set.",
    privateCohort: "K-PREDICT (Private)",
    disease: "Disease",
    panelAlert: "Panel alert",
    carrierOnly: "Carrier only",
    applying: "Loading cohort analysis…",
    applicable: "Applicable individuals",
    cohortSummary: "Cohort summary",
    geneEyebrow: "DISEASE-PANEL FINDINGS",
    geneTableTitle: "Genes with panel findings",
    accessRequired: "K-PREDICT access is required. Return to the Disease Overview and enter an access code.",
    loadFailed: "The cohort analysis could not be loaded.",
    geneHeader: "Gene",
    individualsHeader: "Individuals",
    alertsHeader: "Alerts",
    carriersHeader: "Carriers",
    medianHeader: "Median PRS percentile",
    switchLanguage: "Switch to Korean",
    darkMode: "Dark mode",
    lightMode: "Light mode",
    introEyebrow: "DISEASE-PANEL RARE VARIANTS",
    introTitle: "Rare-Variant Findings Across the Cohort",
    introBody: "For one disease, see which genes carry panel findings in K-PREDICT and where those individuals fall on the PRS distribution.",
    definitionsQuestion: "Definitions and data source",
    distributionEyebrow: "PRS OF INDIVIDUALS WITH PANEL FINDINGS",
    distributionTitle: "Where individuals with panel findings fall on the PRS distribution",
    top10Zone: "Top 10% PRS",
    noFindings: "No individuals have panel findings for this disease.",
    alerts: "With a panel alert",
    carriers: "Carrier only",
    overlap: "Alerts in the top 10% PRS",
    howToRead: "How to read:",
    distributionNote: "Each dot is one individual with a panel finding in that gene, placed at their PRS percentile for this disease. Groups are small, and common-variant PRS and rare panel findings are expected to be largely independent, so clustering at either end should not be over-interpreted.",
    geneTableNote: "Genes observed in the supplied disease-panel findings for K-PREDICT, not the complete panel gene list. Open a gene's individuals in the Disease Overview to see each person's details.",
    top10Header: "In top 10% PRS",
    openHeader: "Open in Overview",
    showIndividuals: "Show individuals",
    noGenes: "No disease-panel findings for this disease.",
    percentileAxis: "PRS percentile (within K-PREDICT)",
    allApplicable: (n) => `${n.toLocaleString()} applicable individuals`,
    overlapValue: (count, total) => `${count} of ${total}${total ? ` (${(count / total * 100).toFixed(0)}%)` : ""}`,
    overlapExpected: (expected) => `About ${expected} expected by chance (10% of alerts), so this alone is not a signal.`,
    pointHover: (gene, status, percentile) => `<b>${gene}</b><br>${status}<br>PRS percentile: ${percentile}`,
  },
  ko: {
    documentTitle: "K-PREDICT 코호트 분석",
    sectionLabel: "K-PREDICT · 코호트 분석",
    pageTitle: "코호트 분석",
    overview: "질환 위험 개요",
    about: "XPRS 소개",
    prsDefinitionLabel: "PRS 백분위",
    prsDefinition: "는 이 코호트의 분석 대상자와 비교한 다유전자 신호를 요약합니다.",
    alertDefinitionLabel: "패널 주의 소견",
    alertDefinition: "은 한 개의 변이 사본으로 작용할 수 있어 원자료에서 우선 검토 대상으로 지정된 소견입니다.",
    carrierDefinitionLabel: "보인자 소견만",
    carrierDefinition: "은 열성 이형접합 소견이며 주의 소견으로 분류되지 않습니다.",
    introBoundary: "이 비교는 기술적 분석입니다. 두 근거를 하나의 점수로 합산하거나 인과관계 또는 진단을 제시하지 않습니다.",
    panelSourceAnswer: "제공받은 파이프라인은 병원성 또는 병원성 가능성이 높은 소견을 Genomics England PanelApp GREEN 패널의 유전자 포함 여부에 따라 질환에 연결했습니다. 이후 PanelApp과 ClinGen의 유전 양식 정보를 이용해 주의 소견 또는 보인자 소견으로 분류했습니다. 포털은 이 원자료 배정을 그대로 사용하며 ClinVar 질환명 텍스트로 질환을 추론하지 않습니다.",
    cardiacPanelCaveat: " PanelApp에는 관상동맥질환이나 심근경색 전용 패널이 없어 제공받은 파이프라인은 가장 가까운 단일유전자 질환 기준으로 가족성 고콜레스테롤혈증 패널을 사용합니다. 따라서 두 질환은 동일한 희귀 변이 유전자 집합을 공유합니다.",
    privateCohort: "K-PREDICT (비공개)",
    disease: "질환",
    panelAlert: "패널 주의 소견",
    carrierOnly: "보인자 소견만",
    applying: "코호트 분석을 불러오는 중…",
    applicable: "분석 대상",
    cohortSummary: "코호트 요약",
    geneEyebrow: "질환 패널 소견",
    geneTableTitle: "패널 소견이 관찰된 유전자",
    accessRequired: "K-PREDICT 접근 권한이 필요합니다. 질환 위험 개요로 돌아가 접근 코드를 입력해 주세요.",
    loadFailed: "코호트 분석을 불러오지 못했습니다.",
    geneHeader: "유전자",
    individualsHeader: "개인 수",
    alertsHeader: "주의",
    carriersHeader: "보인자",
    medianHeader: "PRS 백분위 중앙값",
    switchLanguage: "영어로 전환",
    darkMode: "다크 모드",
    lightMode: "라이트 모드",
    introEyebrow: "질환 패널 희귀 변이",
    introTitle: "코호트의 희귀 변이 소견",
    introBody: "선택한 질환에서 K-PREDICT의 어떤 유전자에 패널 소견이 있는지, 그리고 해당 개인들이 PRS 분포의 어디에 있는지 보여 줍니다.",
    definitionsQuestion: "용어 정의와 자료 출처",
    distributionEyebrow: "패널 소견이 있는 개인의 PRS",
    distributionTitle: "패널 소견이 있는 개인의 PRS 분포상 위치",
    top10Zone: "PRS 상위 10%",
    noFindings: "이 질환에는 패널 소견이 있는 개인이 없습니다.",
    alerts: "패널 주의 소견",
    carriers: "보인자 소견만",
    overlap: "PRS 상위 10%의 주의 소견",
    howToRead: "해석 방법:",
    distributionNote: "각 점은 해당 유전자에 패널 소견이 있는 개인 한 명이며, 이 질환의 PRS 백분위에 표시됩니다. 표본이 작고 다유전자 PRS와 희귀 패널 소견은 대체로 서로 독립적일 것으로 예상되므로, 양 끝에 몰려 보이더라도 과도하게 해석하지 않아야 합니다.",
    geneTableNote: "K-PREDICT 원자료의 질환 패널 소견에서 관찰된 유전자이며, 패널 전체 유전자 목록은 아닙니다. 유전자별 개인을 질환 위험 개요에서 열어 각자의 상세 정보를 볼 수 있습니다.",
    top10Header: "PRS 상위 10%",
    openHeader: "개요에서 열기",
    showIndividuals: "개인 보기",
    noGenes: "이 질환에는 패널 소견이 없습니다.",
    percentileAxis: "PRS 백분위 (K-PREDICT 내)",
    allApplicable: (n) => `분석 대상 ${n.toLocaleString()}명`,
    overlapValue: (count, total) => `${total}명 중 ${count}명${total ? ` (${(count / total * 100).toFixed(0)}%)` : ""}`,
    overlapExpected: (expected) => `우연으로도 약 ${expected}명(주의 소견의 10%)이 예상되므로, 이 수치만으로는 신호가 아닙니다.`,
    pointHover: (gene, status, percentile) => `<b>${gene}</b><br>${status}<br>PRS 백분위: ${percentile}`,
  },
};

const STATUS_STYLE = {
  alert: { color: "#d54b59", symbol: "circle" },
  carrier: { color: "#c98a1d", symbol: "diamond" },
};

function t(key, ...args) {
  const value = TEXT[currentLanguage][key] ?? TEXT.en[key] ?? key;
  return typeof value === "function" ? value(...args) : value;
}

function readPreference(key, fallback) {
  try { return window.localStorage.getItem(key) || fallback; } catch (_error) { return fallback; }
}

function savePreference(key, value) {
  try { window.localStorage.setItem(key, value); } catch (_error) { /* storage is optional */ }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function diseaseLabel(slug) {
  const disease = DISEASES.find(([value]) => value === slug);
  if (!disease) return slug.replaceAll("_", " ");
  return currentLanguage === "ko" ? disease[2] : disease[1];
}

function updatePanelSourceExplanation() {
  const element = $("panel-source-answer");
  if (!element) return;
  const disease = $("disease-filter")?.value || "type2_diabetes";
  const cardiac = disease === "coronary_artery_disease" || disease === "myocardial_infarction";
  element.textContent = t("panelSourceAnswer") + (cardiac ? t("cardiacPanelCaveat") : "");
}

function populateDiseases() {
  const selected = $("disease-filter").value || new URLSearchParams(window.location.search).get("disease") || "type2_diabetes";
  $("disease-filter").replaceChildren(...DISEASES.map(([slug]) => {
    const option = document.createElement("option");
    option.value = slug;
    option.textContent = diseaseLabel(slug);
    option.selected = slug === selected;
    return option;
  }));
}

function applyLanguage(language) {
  currentLanguage = language === "ko" ? "ko" : "en";
  savePreference(LANGUAGE_KEY, currentLanguage);
  document.documentElement.lang = currentLanguage;
  document.title = t("documentTitle");
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  populateDiseases();
  updatePanelSourceExplanation();
  $("language-label").textContent = currentLanguage === "ko" ? "KO" : "EN";
  $("language-toggle").title = t("switchLanguage");
  $("language-toggle").setAttribute("aria-label", t("switchLanguage"));
  if (currentPayload) renderPayload(currentPayload);
}

function applyTheme(theme) {
  currentTheme = theme === "dark" ? "dark" : "light";
  savePreference(THEME_KEY, currentTheme);
  document.documentElement.dataset.theme = currentTheme;
  const nextLabel = currentTheme === "dark" ? t("lightMode") : t("darkMode");
  $("theme-toggle").title = nextLabel;
  $("theme-toggle").setAttribute("aria-label", nextLabel);
  $("theme-icon").textContent = currentTheme === "dark" ? "☀" : "☾";
  if (currentPayload) renderDots(currentPayload);
}

function setStatus(message, isError = false) {
  $("page-status").textContent = message;
  $("page-status").classList.toggle("is-error", isError);
}

function overviewLink(disease, gene) {
  const params = new URLSearchParams({
    cohort: "kpredict",
    finder_disease: disease,
    finder_status: "finding",
    finder_gene: gene,
    language: currentLanguage,
  });
  return `/?${params.toString()}`;
}

function renderGenes(payload) {
  const genes = payload.genes;
  $("gene-table-body").replaceChildren(...genes.map((row) => {
    const tr = document.createElement("tr");
    const cells = [row.gene, row.individual_count, row.alert_count, row.carrier_count,
      row.median_percentile.toFixed(1), row.top_10_percent_count];
    cells.forEach((value, index) => {
      const td = document.createElement("td");
      td.textContent = typeof value === "number" ? value.toLocaleString() : String(value);
      if (index === 0) td.className = "gene-name";
      tr.append(td);
    });
    const action = document.createElement("td");
    const link = document.createElement("a");
    link.className = "gene-button";
    link.href = overviewLink(payload.disease, row.gene);
    link.textContent = t("showIndividuals");
    action.append(link);
    tr.append(action);
    return tr;
  }));
  $("gene-empty").hidden = genes.length > 0;
  $("gene-table-body").closest(".table-wrap").hidden = genes.length === 0;
}

// Dot plot: one dot per individual and gene with a panel finding. Genes are
// rows in gene-table order; a small, deterministic vertical offset separates
// individuals with similar percentiles (no randomness, so reloads match).
function renderDots(payload) {
  const plot = $("distribution-plot");
  const points = payload.points;
  const empty = points.length === 0;
  $("distribution-empty").hidden = !empty;
  plot.hidden = empty;
  if (empty || !window.Plotly) return;
  const dark = currentTheme === "dark";
  const genes = payload.genes.map((row) => row.gene);
  const position = new Map(genes.map((gene, index) => [gene, genes.length - 1 - index]));
  const offsets = new Map();
  const traces = ["alert", "carrier"].map((status) => {
    const selected = points.filter((point) => point.status === status);
    const y = selected.map((point) => {
      const count = offsets.get(point.gene) || 0;
      offsets.set(point.gene, count + 1);
      return position.get(point.gene) + ((count % 5) - 2) * 0.09;
    });
    const label = t(status === "alert" ? "panelAlert" : "carrierOnly");
    return {
      type: "scatter",
      mode: "markers",
      name: label,
      x: selected.map((point) => point.percentile),
      y,
      text: selected.map((point) => t("pointHover", escapeHtml(point.gene), label, point.percentile.toFixed(1))),
      hovertemplate: "%{text}<extra></extra>",
      marker: {
        color: STATUS_STYLE[status].color,
        symbol: STATUS_STYLE[status].symbol,
        size: 10,
        opacity: 0.85,
        line: { color: dark ? "#111827" : "#ffffff", width: 1 },
      },
    };
  });
  const height = Math.max(240, genes.length * 46 + 90);
  plot.style.height = `${height}px`;
  window.Plotly.react(plot, traces, {
    height,
    showlegend: false,
    margin: { l: 130, r: 20, t: 10, b: 52 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Inter, sans-serif", color: dark ? "#cbd5e3" : "#4c5b70", size: 12 },
    shapes: [{
      type: "rect", xref: "x", yref: "paper", x0: 90, x1: 100, y0: 0, y1: 1,
      fillcolor: dark ? "rgba(213, 75, 89, 0.12)" : "rgba(213, 75, 89, 0.08)", line: { width: 0 }, layer: "below",
    }, {
      type: "line", xref: "x", yref: "paper", x0: 50, x1: 50, y0: 0, y1: 1,
      line: { color: dark ? "#52627a" : "#c3ccd8", width: 1, dash: "dot" }, layer: "below",
    }],
    xaxis: { title: t("percentileAxis"), range: [0, 100], dtick: 10, fixedrange: true, gridcolor: dark ? "#2b394d" : "#eef1f5", zeroline: false },
    yaxis: {
      tickvals: genes.map((gene) => position.get(gene)),
      ticktext: genes,
      range: [-0.6, genes.length - 0.4],
      fixedrange: true,
      showgrid: true,
      gridcolor: dark ? "#2b394d" : "#eef1f5",
      zeroline: false,
    },
  }, { responsive: true, displaylogo: false, displayModeBar: false, scrollZoom: false });
}

function renderPayload(payload) {
  currentPayload = payload;
  updatePanelSourceExplanation();
  $("analysis-content").hidden = false;
  const summary = payload.summary;
  $("kpi-applicable").textContent = summary.applicable_count.toLocaleString();
  $("kpi-alerts").textContent = summary.alert_individual_count.toLocaleString();
  $("kpi-carriers").textContent = summary.carrier_individual_count.toLocaleString();
  $("kpi-overlap").textContent = t("overlapValue", summary.top_10_alert_overlap_count, summary.alert_individual_count);
  $("kpi-overlap-expected").textContent = summary.alert_individual_count
    ? t("overlapExpected", summary.top_10_alert_expected_count)
    : "";
  $("distribution-context").textContent = t("allApplicable", summary.applicable_count);
  renderDots(payload);
  renderGenes(payload);
}

async function loadAnalysis() {
  const currentRequest = ++requestId;
  setStatus(t("applying"));
  const params = new URLSearchParams({ disease: $("disease-filter").value });
  try {
    const response = await fetch(`/api/kpredict/cohort-analysis?${params.toString()}`, { cache: "no-store" });
    if (currentRequest !== requestId) return;
    if (response.status === 404) {
      currentPayload = null;
      $("analysis-content").hidden = true;
      setStatus(t("accessRequired"), true);
      return;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    renderPayload(payload);
    setStatus("");
    const url = new URL(window.location.href);
    url.searchParams.set("disease", payload.disease);
    window.history.replaceState({}, "", `${url.pathname}${url.search}`);
  } catch (_error) {
    if (currentRequest === requestId) setStatus(t("loadFailed"), true);
  }
}

window.addEventListener("DOMContentLoaded", () => {
  currentLanguage = readPreference(LANGUAGE_KEY, "en") === "ko" ? "ko" : "en";
  currentTheme = readPreference(THEME_KEY, "light") === "dark" ? "dark" : "light";
  populateDiseases();
  applyLanguage(currentLanguage);
  applyTheme(currentTheme);
  loadAnalysis();
  $("disease-filter").addEventListener("change", () => {
    updatePanelSourceExplanation();
    loadAnalysis();
  });
  $("language-toggle").addEventListener("click", () => applyLanguage(currentLanguage === "en" ? "ko" : "en"));
  $("theme-toggle").addEventListener("click", () => applyTheme(currentTheme === "light" ? "dark" : "light"));
  window.addEventListener("storage", (event) => {
    if (event.key === LANGUAGE_KEY && event.newValue) applyLanguage(event.newValue);
    if (event.key === THEME_KEY && event.newValue) applyTheme(event.newValue);
  });
});
