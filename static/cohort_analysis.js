const $ = (id) => document.getElementById(id);

const LANGUAGE_KEY = "xprs.language";
const THEME_KEY = "xprs.theme";
let currentLanguage = "en";
let currentTheme = "light";
let currentPayload = null;
let requestId = 0;
let appliedFilters = {
  rareStatus: "all",
  percentileBand: "all",
  gene: "",
  consequence: "",
};

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

const BANDS = {
  all: [0, 100],
  top_5: [95, 100],
  top_10: [90, 100],
  top_25: [75, 100],
  bottom_25: [0, 25],
  bottom_10: [0, 10],
  bottom_5: [0, 5],
};

const TEXT = {
  en: {
    documentTitle: "K-PREDICT Cohort Analysis",
    sectionLabel: "K-PREDICT · Population view",
    pageTitle: "Cohort Analysis",
    overview: "Disease overview",
    about: "About XPRS",
    introEyebrow: "COMMON + RARE VARIANT EVIDENCE",
    introTitle: "PRS and Rare-Variant Cohort Analysis",
    introQuestion: "Do common- and rare-variant signals occur in the same individuals?",
    introBody: "For the selected disease, this page compares PRS percentiles with rare-variant findings that the supplied K-PREDICT data explicitly assigned to that disease panel.",
    prsDefinitionLabel: "PRS percentile",
    prsDefinition: " summarizes common-variant signal relative to applicable individuals in this cohort.",
    alertDefinitionLabel: "Panel alert",
    alertDefinition: " is a supplied finding that may act with one copy and was designated for prominent review.",
    carrierDefinitionLabel: "Carrier only",
    carrierDefinition: " is a supplied recessive heterozygous finding and is not classified as an alert.",
    introBoundary: "The comparison is descriptive. It does not combine the two evidence types, establish causation, or provide a diagnosis.",
    panelSourceQuestion: "How were disease-panel findings defined?",
    panelSourceAnswer: "The supplied pipeline mapped pathogenic or likely pathogenic findings to diseases by gene membership in Genomics England PanelApp GREEN panels. PanelApp and ClinGen modes of inheritance were then used to classify each finding as an alert or carrier. The portal preserves those supplied assignments and does not infer them from ClinVar condition text.",
    cardiacPanelCaveat: " PanelApp has no dedicated coronary artery disease or myocardial infarction panel, so the supplied pipeline uses the Familial hypercholesterolaemia panel as the closest monogenic analogue; these two diseases therefore share the same rare-variant gene set.",
    privateCohort: "K-PREDICT (Private)",
    filters: "Analysis filters",
    filtersHelp: "Changing the disease refreshes immediately. Use Apply filters for the other selections.",
    updatesImmediately: "Updates immediately",
    applyTogether: "Apply together",
    changesPending: "Changes not applied",
    reset: "Reset",
    disease: "Disease",
    rareStatus: "Rare-variant status",
    allStatuses: "All statuses",
    panelAlert: "Panel alert",
    carrierOnly: "Carrier only",
    noPanelFinding: "No panel finding",
    percentileBand: "PRS percentile band",
    allPercentiles: "All percentiles",
    top5: "Top 5%", top10: "Top 10%", top25: "Top 25%",
    bottom25: "Bottom 25%", bottom10: "Bottom 10%", bottom5: "Bottom 5%",
    gene: "Gene with a panel finding", allGenes: "All genes",
    consequence: "Molecular consequence", allConsequences: "All consequences",
    apply: "Apply filters",
    applying: "Loading cohort analysis…",
    applicable: "Applicable individuals",
    alerts: "Individuals with a panel alert",
    carriers: "Carrier-only individuals",
    noPanelFindingIndividuals: "Individuals without a panel finding",
    overlap: "Alert individuals in the top 10% PRS",
    cohortSummary: "Cohort summary",
    summaryScope: "Counts use distinct applicable individuals and only the selected disease's supplied panel assignments.",
    distributionEyebrow: "COHORT DISTRIBUTION",
    distributionTitle: "PRS percentile by rare-variant status",
    howToRead: "How to read the plot:",
    distributionNote: "Each curve is the cumulative PRS-percentile distribution for one rare-variant group. A curve lying farther to the right indicates generally higher PRS percentiles. Small alert or carrier groups should be interpreted cautiously.",
    geneEyebrow: "DISEASE-PANEL FINDINGS",
    geneTableTitle: "Genes with panel findings",
    geneTableNote: "These are genes observed in the supplied disease-panel findings after applying the filters—not a complete list of genes in the disease panel.",
    drilldownEyebrow: "FILTERED DRILL-DOWN",
    individualTableTitle: "Matching individuals",
    geneHeader: "Gene", individualsHeader: "Individuals", alertsHeader: "Alerts", carriersHeader: "Carriers",
    medianHeader: "Median PRS percentile", top10Header: "Top 10%",
    individualHeader: "Individual", percentileHeader: "PRS percentile", statusHeader: "Rare-variant status", genesHeader: "Panel genes",
    noGenes: "No disease-panel genes match these filters.",
    noIndividuals: "No individuals match these filters.",
    accessRequired: "K-PREDICT access is required. Return to the Disease Overview and enter an access code.",
    loadFailed: "The cohort analysis could not be loaded.",
    allApplicable: (n) => `${n.toLocaleString()} applicable individuals`,
    matchCount: (matches, shown) => shown < matches ? `${matches.toLocaleString()} matched · first ${shown.toLocaleString()} shown` : `${matches.toLocaleString()} matched`,
    switchLanguage: "Switch to Korean", darkMode: "Dark mode", lightMode: "Light mode",
    cumulative: "Cumulative share (%)", percentileAxis: "Within-cohort PRS percentile",
    individualsInBin: "Individuals in 5-point bin",
  },
  ko: {
    documentTitle: "K-PREDICT 코호트 분석",
    sectionLabel: "K-PREDICT · 코호트 분석",
    pageTitle: "코호트 분석",
    overview: "질환 위험 개요",
    about: "XPRS 소개",
    introEyebrow: "다유전자·희귀 변이 근거",
    introTitle: "PRS·희귀 변이 코호트 분석",
    introQuestion: "다유전자 신호와 희귀 변이 소견이 같은 개인에게 함께 나타나는가?",
    introBody: "선택한 질환에서 PRS 백분위와 K-PREDICT 원자료가 해당 질환 패널에 명시적으로 배정한 희귀 변이 소견을 비교합니다.",
    prsDefinitionLabel: "PRS 백분위",
    prsDefinition: "는 이 코호트의 분석 대상자와 비교한 다유전자 신호를 요약합니다.",
    alertDefinitionLabel: "패널 주의 소견",
    alertDefinition: "은 한 개의 변이 사본으로 작용할 수 있어 원자료에서 우선 검토 대상으로 지정된 소견입니다.",
    carrierDefinitionLabel: "보인자 소견만",
    carrierDefinition: "은 열성 이형접합 소견이며 주의 소견으로 분류되지 않습니다.",
    introBoundary: "이 비교는 기술적 분석입니다. 두 근거를 하나의 점수로 합산하거나 인과관계 또는 진단을 제시하지 않습니다.",
    panelSourceQuestion: "질환 패널 소견은 어떻게 정의했나요?",
    panelSourceAnswer: "제공받은 파이프라인은 병원성 또는 병원성 가능성이 높은 소견을 Genomics England PanelApp GREEN 패널의 유전자 포함 여부에 따라 질환에 연결했습니다. 이후 PanelApp과 ClinGen의 유전 양식 정보를 이용해 주의 소견 또는 보인자 소견으로 분류했습니다. 포털은 이 원자료 배정을 그대로 사용하며 ClinVar 질환명 텍스트로 질환을 추론하지 않습니다.",
    cardiacPanelCaveat: " PanelApp에는 관상동맥질환이나 심근경색 전용 패널이 없어 제공받은 파이프라인은 가장 가까운 단일유전자 질환 기준으로 가족성 고콜레스테롤혈증 패널을 사용합니다. 따라서 두 질환은 동일한 희귀 변이 유전자 집합을 공유합니다.",
    privateCohort: "K-PREDICT (비공개)",
    filters: "분석 조건",
    filtersHelp: "질환을 변경하면 즉시 새로고침됩니다. 나머지 조건은 조건 적용 버튼을 눌러 반영합니다.",
    updatesImmediately: "즉시 반영",
    applyTogether: "한꺼번에 적용",
    changesPending: "변경 사항 미적용",
    reset: "초기화",
    disease: "질환",
    rareStatus: "희귀 변이 상태",
    allStatuses: "전체 상태",
    panelAlert: "패널 주의 소견",
    carrierOnly: "보인자 소견만",
    noPanelFinding: "패널 소견 없음",
    percentileBand: "PRS 백분위 구간",
    allPercentiles: "전체 백분위",
    top5: "상위 5%", top10: "상위 10%", top25: "상위 25%",
    bottom25: "하위 25%", bottom10: "하위 10%", bottom5: "하위 5%",
    gene: "패널 소견이 있는 유전자", allGenes: "전체 유전자",
    consequence: "분자적 결과", allConsequences: "전체 결과",
    apply: "조건 적용",
    applying: "코호트 분석을 불러오는 중…",
    applicable: "분석 대상",
    alerts: "패널 주의 소견이 있는 개인",
    carriers: "보인자 소견만 있는 개인",
    noPanelFindingIndividuals: "패널 소견이 없는 개인",
    overlap: "PRS 상위 10%에 속한 주의 소견 개인",
    cohortSummary: "코호트 요약",
    summaryScope: "선택한 질환에 대해 분석 가능한 개인과 원자료의 패널 배정만 집계합니다.",
    distributionEyebrow: "코호트 분포",
    distributionTitle: "희귀 변이 상태별 PRS 백분위",
    howToRead: "플롯 해석 방법:",
    distributionNote: "각 곡선은 희귀 변이 그룹별 PRS 백분위의 누적 분포입니다. 곡선이 더 오른쪽에 있으면 해당 그룹의 PRS 백분위가 전반적으로 더 높다는 뜻입니다. 주의 소견 또는 보인자 그룹의 표본 수가 작을 때는 신중하게 해석해야 합니다.",
    geneEyebrow: "질환 패널 소견",
    geneTableTitle: "패널 소견이 관찰된 유전자",
    geneTableNote: "조건 적용 후 원자료의 질환 패널 소견에서 실제로 관찰된 유전자입니다. 해당 질환 패널의 전체 유전자 목록이 아닙니다.",
    drilldownEyebrow: "조건별 상세 조회",
    individualTableTitle: "조건에 맞는 개인",
    geneHeader: "유전자", individualsHeader: "개인 수", alertsHeader: "주의", carriersHeader: "보인자",
    medianHeader: "PRS 백분위 중앙값", top10Header: "상위 10%",
    individualHeader: "개인", percentileHeader: "PRS 백분위", statusHeader: "희귀 변이 상태", genesHeader: "패널 유전자",
    noGenes: "이 조건에 해당하는 질환 패널 유전자가 없습니다.",
    noIndividuals: "이 조건에 해당하는 개인이 없습니다.",
    accessRequired: "K-PREDICT 접근 권한이 필요합니다. 질환 위험 개요로 돌아가 접근 코드를 입력해 주세요.",
    loadFailed: "코호트 분석을 불러오지 못했습니다.",
    allApplicable: (n) => `분석 대상 ${n.toLocaleString()}명`,
    matchCount: (matches, shown) => shown < matches ? `${matches.toLocaleString()}명 해당 · ${shown.toLocaleString()}명 표시` : `${matches.toLocaleString()}명 해당`,
    switchLanguage: "영어로 전환", darkMode: "다크 모드", lightMode: "라이트 모드",
    cumulative: "누적 비율 (%)", percentileAxis: "코호트 내 PRS 백분위",
    individualsInBin: "5백분위 구간 개인 수",
  },
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

function applyLanguage(language, { reload = false } = {}) {
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
  if (reload) loadAnalysis();
}

function applyTheme(theme) {
  currentTheme = theme === "dark" ? "dark" : "light";
  savePreference(THEME_KEY, currentTheme);
  document.documentElement.dataset.theme = currentTheme;
  const nextLabel = currentTheme === "dark" ? t("lightMode") : t("darkMode");
  $("theme-toggle").title = nextLabel;
  $("theme-toggle").setAttribute("aria-label", nextLabel);
  $("theme-icon").textContent = currentTheme === "dark" ? "☀" : "☾";
  if (currentPayload) renderDistribution(currentPayload);
}

function setStatus(message, isError = false) {
  $("page-status").textContent = message;
  $("page-status").classList.toggle("is-error", isError);
}

function updateSelectOptions(id, values, label) {
  const select = $(id);
  const current = select.value;
  const first = document.createElement("option");
  first.value = "";
  first.textContent = label;
  const options = values.map((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value.replaceAll("_", " ");
    return option;
  });
  select.replaceChildren(first, ...options);
  select.value = values.includes(current) ? current : "";
}

function statusBadge(status) {
  const badge = document.createElement("span");
  badge.className = `status-badge status-${status}`;
  badge.textContent = t(status === "alert" ? "panelAlert" : status === "carrier" ? "carrierOnly" : "noPanelFinding");
  return badge;
}

function readStagedFilters() {
  return {
    rareStatus: $("status-filter").value,
    percentileBand: $("percentile-filter").value,
    gene: $("gene-filter").value,
    consequence: $("consequence-filter").value,
  };
}

function filtersMatch(left, right) {
  return Object.keys(appliedFilters).every((key) => left[key] === right[key]);
}

function syncPendingFilterState() {
  const pending = !filtersMatch(readStagedFilters(), appliedFilters);
  $("staged-filter-group")?.classList.toggle("has-pending-changes", pending);
  if ($("pending-filter-indicator")) $("pending-filter-indicator").hidden = !pending;
}

function commitStagedFilters() {
  appliedFilters = readStagedFilters();
  syncPendingFilterState();
}

function renderGenes(genes) {
  const tbody = $("gene-table-body");
  tbody.replaceChildren(...genes.map((row) => {
    const tr = document.createElement("tr");
    const geneCell = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "gene-button";
    button.textContent = row.gene;
    button.addEventListener("click", () => {
      $("gene-filter").value = row.gene;
      commitStagedFilters();
      loadAnalysis(appliedFilters);
    });
    geneCell.append(button);
    const values = [row.individual_count, row.alert_count, row.carrier_count, row.median_percentile.toFixed(1), row.top_10_percent_count];
    tr.append(geneCell, ...values.map((value) => {
      const td = document.createElement("td"); td.textContent = value.toLocaleString?.() ?? String(value); return td;
    }));
    return tr;
  }));
  $("gene-empty").hidden = genes.length > 0;
  tbody.closest(".table-wrap").hidden = genes.length === 0;
}

function renderIndividuals(filtered) {
  const disease = $("disease-filter").value;
  const tbody = $("individual-table-body");
  tbody.replaceChildren(...filtered.individuals.map((row) => {
    const tr = document.createElement("tr");
    const idCell = document.createElement("td");
    const link = document.createElement("a");
    link.className = "individual-link";
    link.textContent = row.individual_id;
    link.href = `/?${new URLSearchParams({ cohort: "kpredict", individual_id: row.individual_id, language: currentLanguage, disease }).toString()}`;
    idCell.append(link);
    const percentile = document.createElement("td"); percentile.textContent = row.percentile.toFixed(1);
    const status = document.createElement("td"); status.append(statusBadge(row.rare_status));
    const genes = document.createElement("td"); genes.className = "genes-cell"; genes.textContent = row.genes.join(", ") || "—";
    tr.append(idCell, percentile, status, genes);
    return tr;
  }));
  $("individual-count").textContent = t("matchCount", filtered.matching_count, filtered.returned_count);
  $("individual-empty").hidden = filtered.individuals.length > 0;
  tbody.closest(".table-wrap").hidden = filtered.individuals.length === 0;
}

function renderDistribution(payload) {
  if (!window.Plotly) return;
  const colors = { alert: "#d54b59", carrier: "#d19a35", none: currentTheme === "dark" ? "#8ca2bf" : "#617895" };
  const traces = payload.distribution.groups.map((group) => ({
    type: "scatter",
    mode: "lines",
    name: `${t(group.status === "alert" ? "panelAlert" : group.status === "carrier" ? "carrierOnly" : "noPanelFinding")} (n=${group.count.toLocaleString()})`,
    x: [0, ...group.bin_upper_bounds],
    y: [0, ...group.cumulative_percent],
    customdata: [0, ...group.bin_counts],
    line: { color: colors[group.status], width: 3, shape: "hv" },
    hovertemplate: `<b>%{fullData.name}</b><br>${t("percentileAxis")}: ≤ %{x:.0f}<br>${t("cumulative")}: %{y:.1f}%<br>${t("individualsInBin")}: %{customdata}<extra></extra>`,
  }));
  const dark = currentTheme === "dark";
  window.Plotly.react("distribution-plot", traces, {
    margin: { l: 58, r: 22, t: 22, b: 58 },
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Inter, sans-serif", color: dark ? "#cbd5e3" : "#4c5b70", size: 12 },
    hovermode: "x unified",
    legend: { orientation: "h", x: 0, y: 1.11, bgcolor: "rgba(0,0,0,0)" },
    xaxis: { title: t("percentileAxis"), range: [0, 100], dtick: 10, fixedrange: true, gridcolor: dark ? "#2b394d" : "#e7ebf1", zeroline: false },
    yaxis: { title: t("cumulative"), range: [0, 100], dtick: 20, fixedrange: true, gridcolor: dark ? "#2b394d" : "#e7ebf1", zeroline: false },
  }, { responsive: true, displaylogo: false, displayModeBar: false, scrollZoom: false });
}

function renderPayload(payload) {
  currentPayload = payload;
  updatePanelSourceExplanation();
  $("analysis-content").hidden = false;
  $("kpi-applicable").textContent = payload.summary.applicable_count.toLocaleString();
  $("kpi-alerts").textContent = payload.summary.alert_individual_count.toLocaleString();
  $("kpi-carriers").textContent = payload.summary.carrier_individual_count.toLocaleString();
  $("kpi-none").textContent = payload.summary.no_panel_finding_count.toLocaleString();
  const alertCount = payload.summary.alert_individual_count;
  const overlapCount = payload.summary.top_10_alert_overlap_count;
  const overlapPercent = alertCount ? (overlapCount / alertCount * 100).toFixed(1) : "0.0";
  $("kpi-overlap").textContent = `${overlapCount.toLocaleString()} / ${alertCount.toLocaleString()} (${overlapPercent}%)`;
  $("distribution-context").textContent = `${diseaseLabel(payload.disease)} · ${t("allApplicable", payload.summary.applicable_count)}`;
  updateSelectOptions("gene-filter", payload.filter_options.genes, t("allGenes"));
  updateSelectOptions("consequence-filter", payload.filter_options.consequences, t("allConsequences"));
  syncPendingFilterState();
  renderDistribution(payload);
  renderGenes(payload.filtered.genes);
  renderIndividuals(payload.filtered);
}

async function loadAnalysis(filters = appliedFilters) {
  const currentRequest = ++requestId;
  const button = $("apply-filters");
  button.disabled = true;
  setStatus(t("applying"));
  const [minimum, maximum] = BANDS[filters.percentileBand] || BANDS.all;
  const params = new URLSearchParams({
    disease: $("disease-filter").value,
    rare_status: filters.rareStatus,
    percentile_min: minimum,
    percentile_max: maximum,
    gene: filters.gene,
    consequence: filters.consequence,
    individual_limit: 200,
  });
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
  } finally {
    if (currentRequest === requestId) button.disabled = false;
  }
}

function resetFilters() {
  $("status-filter").value = "all";
  $("percentile-filter").value = "all";
  $("gene-filter").value = "";
  $("consequence-filter").value = "";
  commitStagedFilters();
  loadAnalysis(appliedFilters);
}

window.addEventListener("DOMContentLoaded", () => {
  currentLanguage = readPreference(LANGUAGE_KEY, "en") === "ko" ? "ko" : "en";
  currentTheme = readPreference(THEME_KEY, "light") === "dark" ? "dark" : "light";
  populateDiseases();
  applyLanguage(currentLanguage);
  applyTheme(currentTheme);
  loadAnalysis(appliedFilters);
  $("analysis-form").addEventListener("submit", (event) => {
    event.preventDefault();
    commitStagedFilters();
    loadAnalysis(appliedFilters);
  });
  $("disease-filter").addEventListener("change", () => {
    $("gene-filter").value = "";
    $("consequence-filter").value = "";
    appliedFilters = { ...appliedFilters, gene: "", consequence: "" };
    updatePanelSourceExplanation();
    syncPendingFilterState();
    loadAnalysis(appliedFilters);
  });
  ["status-filter", "percentile-filter", "gene-filter", "consequence-filter"].forEach((id) => {
    $(id)?.addEventListener("change", syncPendingFilterState);
  });
  $("reset-filters").addEventListener("click", resetFilters);
  $("language-toggle").addEventListener("click", () => applyLanguage(currentLanguage === "en" ? "ko" : "en"));
  $("theme-toggle").addEventListener("click", () => applyTheme(currentTheme === "light" ? "dark" : "light"));
  window.addEventListener("storage", (event) => {
    if (event.key === LANGUAGE_KEY && event.newValue) applyLanguage(event.newValue);
    if (event.key === THEME_KEY && event.newValue) applyTheme(event.newValue);
  });
});
