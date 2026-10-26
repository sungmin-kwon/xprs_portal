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
let privateAccessPromptShown = false;
let individualSearchIndex = [];
let individualSearchTimer = null;
let renderedIndividualKey = "";
let geneHeatmapData = null;
let populationGeneArchitectureData = null;
let geneHeatmapRequestId = 0;
let populationArchitectureRequestId = 0;
let activeGeneComparisonView = "individual";
let riskFilteredIndividuals = null;
let riskPercentileById = new Map();
let activeRiskFilter = null;
let riskFilterRequestId = 0;
let rareOverviewData = null;
let rareOverviewRequestId = 0;
let diseaseOverviewRequestId = 0;
let rareTooltipAnchor = null;
let rareTooltipPinned = false;

const LANGUAGE_PREFERENCE_KEY = "xprs.language";
const THEME_PREFERENCE_KEY = "xprs.theme";
const INDIVIDUAL_PREFERENCE_KEY = "xprs.individual_id";
const INDIVIDUAL_SEARCH_LIMIT = 200;
const INDIVIDUAL_SEARCH_DEBOUNCE_MS = 120;
const OVERVIEW_NETWORK_RETRY_DELAYS_MS = [0, 400, 1200];
const RISK_BANDS = {
  top_1: { minimum: 99, maximum: 100 },
  top_5: { minimum: 95, maximum: 100 },
  top_10: { minimum: 90, maximum: 100 },
  top_25: { minimum: 75, maximum: 100 },
  middle_50: { minimum: 25, maximum: 75 },
  bottom_25: { minimum: 0, maximum: 25 },
  bottom_10: { minimum: 0, maximum: 10 },
  bottom_5: { minimum: 0, maximum: 5 },
  bottom_1: { minimum: 0, maximum: 1 },
  all: { minimum: 0, maximum: 100 },
};
const RISK_BAND_TEXT_KEYS = {
  top_1: "riskBandTop1",
  top_5: "riskBandTop5",
  top_10: "riskBandTop10",
  top_25: "riskBandTop25",
  middle_50: "riskBandMiddle50",
  bottom_25: "riskBandBottom25",
  bottom_10: "riskBandBottom10",
  bottom_5: "riskBandBottom5",
  bottom_1: "riskBandBottom1",
  all: "riskBandAll",
};

const UI_TEXT = {
  en: {
    documentTitle: "XPRS Disease Overview",
    diseaseNavigation: "Disease navigation",
    portalTitle: "XPRS Portal",
    diseaseOverview: "Disease overview",
    breastCancerPortal: "Breast cancer portal",
    userEvaluation: "User evaluation survey",
    pageTitle: "XPRS Disease Overview",
    cohortAnalysis: "Cohort Analysis",
    aboutXprs: "About XPRS",
    individualSelection: "Individual Selection",
    cohort: "Cohort",
    availableCohorts: "Available cohorts",
    individualId: "ID",
    searchIndividualId: "Search individual ID",
    availableIndividualIds: "Individual ID list",
    riskOverview: "Overall Individual Risk Overview",
    singleDiseaseRiskOverview: "Breast Cancer Risk Overview",
    refreshRiskCards: "Refresh risk cards",
    switchToKorean: "Switch to Korean",
    switchToEnglish: "Switch to English",
    darkMode: "Dark mode",
    lightMode: "Light mode",
    loadingCohorts: "Loading cohorts...",
    loadingIndividuals: "Loading individuals...",
    loadingDiseaseWorkspaces: "Loading disease data...",
    loadingRiskCards: "Loading risk density cards...",
    noDiseaseWorkspaces: "No diseases are configured.",
    noModelData: "No data available yet.",
    modelDataUnavailable: "No data available for this disease.",
    prsNotApplicable: "The PRS model is not applicable to this individual.",
    prsUnavailableStatus: "PRS unavailable",
    cohortDataUnavailable: "No data available for this cohort.",
    available: "Available",
    unavailable: "Unavailable",
    percentile: "Percentile",
    riskTintLegend: "Plot shading reflects the individual's within-cohort PRS percentile",
    lowerPrsPercentile: "Lower PRS percentile",
    higherPrsPercentile: "Higher PRS percentile",
    portalLoadFailed: "Failed to load portal data",
    overviewConnectionFailed: "The connection was interrupted while loading this individual. Please refresh the overview.",
    individualCount: (count, shown = count) => shown < count
      ? `${count} individuals found · showing first ${shown}`
      : `${count} individual${count === 1 ? "" : "s"} found`,
    failedToLoadCohorts: (status) => `Failed to load cohorts: HTTP ${status}`,
    failedToLoadDiseases: (status) => `Failed to load diseases: HTTP ${status}`,
    failedToLoadIndividuals: (status) => `Failed to load individuals: HTTP ${status}`,
    privateAccessRequired: "Enter the K-PREDICT access code to view private cohort data.",
    privateAccessPrompt: "K-PREDICT access code",
    privateAccessFailed: "The K-PREDICT access code was not accepted.",
    restrictedCohort: "Restricted cohort",
    kpredictAccessTitle: "Access K-PREDICT",
    kpredictAccessSubtitle: "Enter a K-PREDICT or administrator access code to continue.",
    accessCode: "Access code",
    accessCodePlaceholder: "Enter access code",
    accessCodeRequired: "Enter an access code.",
    checkingAccessCode: "Checking access code...",
    continueAction: "Continue",
    closeKpredictAccess: "Close K-PREDICT access dialog",
    findIndividualsByRisk: "Find individuals by risk",
    clearRiskFilter: "Clear disease-risk filter",
    cohortFinder: "Cohort finder",
    riskFilterTitle: "Find Individuals by Disease Risk",
    riskFilterSubtitle: "Filter the full K-PREDICT cohort using disease-specific percentiles.",
    closeRiskFilter: "Close risk filter",
    diseaseModel: "Disease model",
    percentileBand: "Percentile band",
    resultOrder: "Result order",
    riskBandTop1: "Top 1%",
    riskBandTop5: "Top 5%",
    riskBandTop10: "Top 10%",
    riskBandTop25: "Top 25%",
    riskBandMiddle50: "Middle 50%",
    riskBandBottom25: "Bottom 25%",
    riskBandBottom10: "Bottom 10%",
    riskBandBottom5: "Bottom 5%",
    riskBandBottom1: "Bottom 1%",
    riskBandAll: "All applicable individuals",
    highestFirst: "Highest percentile first",
    lowestFirst: "Lowest percentile first",
    cancel: "Cancel",
    applyRiskFilter: "Apply filter",
    applyingRiskFilter: "Searching the full cohort...",
    riskFilterFailed: "The disease-risk filter could not be applied.",
    riskFilterNote: "Percentiles describe position within the disease-specific applicable K-PREDICT reference population. They are not absolute disease probabilities.",
    riskFilterSummary: (disease, band, count) => `${disease} · ${band} · ${count} individual${count === 1 ? "" : "s"}`,
    riskFilterResult: (count, applicable) => `${count} of ${applicable} applicable individuals match this filter.`,
    riskFilteredIndividualCount: (matches, total, shown = matches) => {
      const narrowed = matches < total ? `${matches} ID match${matches === 1 ? "" : "es"} within ${total} risk-filtered individuals` : `${total} risk-filtered individual${total === 1 ? "" : "s"}`;
      return shown < matches ? `${narrowed} · showing first ${shown}` : narrowed;
    },
    individualFindings: "Individual findings",
    rareVariantOverview: "Rare Variants",
    loadingRareVariants: "Loading rare variants...",
    rareOverviewLoadFailed: "Rare-variant findings could not be loaded.",
    rareOverviewNoFindings: "No curated rare-variant findings are recorded for this individual.",
    rareOverviewSelectIndividual: "Select an individual to view rare-variant findings.",
    rareOverviewGeneCount: (count) => `${count} gene${count === 1 ? "" : "s"}`,
    rareOverviewAlertGenes: (count) => `${count} with ${count === 1 ? "an alert" : "alerts"}`,
    rareOverviewCarrierGenes: (count) => `${count} with a carrier finding`,
    rareOverviewVariantCount: (count) => `${count} unique variant${count === 1 ? "" : "s"}`,
    rareAlertHelpLabel: "What does alert mean?",
    rareAlertHelp: "An alert is a finding the data provider designated for prominent review. It is not a diagnosis.",
    rareCarrierHelpLabel: "What does carrier mean?",
    rareCarrierHelp: "A carrier finding is a heterozygous variant associated with a recessive condition. It generally indicates carrier status, not that the individual has the condition.",
    rareAlert: "Alert",
    rareCarrier: "Carrier",
    rareFinding: "Finding",
    rareOther: "Other",
    viewRareDetails: "View rare-variant details",
    rarePanelAssignments: (count) => `${count} disease panel${count === 1 ? "" : "s"}`,
    diseaseLinkedRareFindings: "Disease-linked rare findings",
    cardAlertCount: (count) => `${count} alert${count === 1 ? "" : "s"}`,
    cardCarrierCount: (count) => `${count} carrier finding${count === 1 ? "" : "s"}`,
    separateRareEvidence: "Separate rare-variant evidence",
    cardPanelAlertCount: (count) => `Rare-variant panel · ${count} alert${count === 1 ? "" : "s"}`,
    cardPanelCarrierCount: (count) => `Rare-variant panel · ${count} carrier finding${count === 1 ? "" : "s"}`,
    rareEvidenceWithoutPrsHelp: "This supplied disease-panel finding is separate from the unavailable PRS model and does not provide a PRS percentile.",
    geneHeatmap: "Gene Heatmap",
    exploratoryAnalysis: "Cross-Disease Comparison",
    geneHeatmapTitle: "Gene Contributions Across Diseases",
    closeGeneHeatmap: "Close gene comparison",
    geneHeatmapLoading: "Comparing gene contributions across diseases...",
    geneHeatmapFailed: "The gene contribution comparison could not be loaded.",
    geneHeatmapPlotlyUnavailable: "The gene heatmap could not be displayed.",
    geneHeatmapScale: "Standardized gene contribution (SD)",
    geneHeatmapMissingValue: "No standardized contribution available",
    geneHeatmapSubtitle: (pid, count) => `${pid} · ${count} disease models included`,
    geneHeatmapMethod: (fraction, minimum, maximum, candidates, unavailable) => {
      const excluded = unavailable
        ? ` ${unavailable} disease model${unavailable === 1 ? " is" : "s are"} not applicable to this individual and ${unavailable === 1 ? "is" : "are"} excluded.`
        : "";
      return `Genes are included when their absolute standardized contribution ranks in the top ${fraction}% for at least ${minimum} diseases. The chart shows up to ${maximum} of ${candidates} qualifying genes, prioritizing genes found across more diseases and those with larger contributions. Each cell is the gene contribution divided by the square root of its population variance. Positive values raise the PRS; negative values lower it. To keep extreme values from flattening the rest of the chart, the color scale is capped at the 95th percentile of absolute values; hover over a cell for its exact value. Gray cells indicate that no standardized contribution was available for that gene–disease pair; they are not zeros.${excluded} This is an exploratory comparison of shared contribution patterns, not evidence of biological interaction, and it does not combine diseases into a single risk score.`;
    },
    geneComparisonView: "Gene comparison view",
    individualGeneProfile: "Selected Individual",
    populationArchitecture: "Population Architecture",
    prototype: "Prototype",
    architectureThreshold: "High-variance threshold",
    architectureMinimumDiseases: "Shared across at least",
    topTwoPointFivePercent: "Top 2.5%",
    topOnePercent: "Top 1%",
    topHalfPercent: "Top 0.5%",
    twoDiseases: "2 diseases",
    threeDiseases: "3 diseases",
    fourDiseases: "4 diseases",
    updateComparison: "Update comparison",
    populationArchitectureLoading: "Comparing population gene architecture across disease models...",
    populationArchitectureFailed: "The population gene-architecture comparison could not be loaded.",
    populationArchitectureScale: "Population variance percentile",
    populationRawVariance: "Raw population variance",
    populationArchitectureMissing: "Gene not available in this disease model",
    populationArchitectureSubtitle: (count) => `${count} K-PREDICT disease models`,
    populationArchitectureMethod: (threshold, minimum, shown, candidates) => `This prototype compares each gene's population contribution variance with other genes in the same disease model. It shows ${shown} of ${candidates} genes that rank in the top ${(100 - threshold).toFixed(threshold % 1 ? 1 : 0)}% for at least ${minimum} diseases. A value of 99 means that the gene has greater contribution variance than approximately 99% of genes in that disease model. This is a comparison of the supplied PRS models—not evidence that a gene causes, connects, or predicts the diseases.`,
  },
  ko: {
    documentTitle: "XPRS 질환 위험 개요",
    diseaseNavigation: "질환 탐색",
    portalTitle: "XPRS 포털",
    diseaseOverview: "질환 위험 개요",
    breastCancerPortal: "유방암 포털",
    userEvaluation: "사용성 평가 설문",
    pageTitle: "XPRS 질환 위험 개요",
    cohortAnalysis: "코호트 분석",
    aboutXprs: "XPRS 소개",
    individualSelection: "개인 선택",
    cohort: "코호트",
    availableCohorts: "코호트 목록",
    individualId: "개인 ID",
    searchIndividualId: "개인 ID 검색",
    availableIndividualIds: "개인 ID 목록",
    riskOverview: "개인별 질환 위험 개요",
    singleDiseaseRiskOverview: "유방암 위험 개요",
    refreshRiskCards: "위험 카드 새로고침",
    switchToKorean: "한국어로 전환",
    switchToEnglish: "영어로 전환",
    darkMode: "다크 모드",
    lightMode: "라이트 모드",
    loadingCohorts: "코호트 불러오는 중...",
    loadingIndividuals: "개인 목록 불러오는 중...",
    loadingDiseaseWorkspaces: "질환 정보를 불러오는 중...",
    loadingRiskCards: "위험 분포 카드 불러오는 중...",
    noDiseaseWorkspaces: "표시할 질환이 없습니다.",
    noModelData: "아직 데이터가 없습니다.",
    modelDataUnavailable: "이 질환에 해당하는 데이터가 없습니다.",
    prsNotApplicable: "이 개인에게는 PRS 모델이 적용되지 않습니다.",
    prsUnavailableStatus: "PRS 적용 불가",
    cohortDataUnavailable: "이 코호트에 해당하는 데이터가 없습니다.",
    available: "조회 가능",
    unavailable: "데이터 없음",
    percentile: "백분위",
    riskTintLegend: "플롯 음영은 코호트 내 개인의 PRS 백분위를 나타냅니다",
    lowerPrsPercentile: "낮은 PRS 백분위",
    higherPrsPercentile: "높은 PRS 백분위",
    portalLoadFailed: "포털 데이터를 불러오지 못했습니다",
    overviewConnectionFailed: "개인 데이터를 불러오는 중 연결이 끊겼습니다. 개요를 새로고침해 주세요.",
    individualCount: (count, shown = count) => shown < count
      ? `총 ${count}명 · 처음 ${shown}명 표시`
      : `총 ${count}명`,
    failedToLoadCohorts: (status) => `코호트를 불러오지 못했습니다: HTTP ${status}`,
    failedToLoadDiseases: (status) => `질환 목록을 불러오지 못했습니다: HTTP ${status}`,
    failedToLoadIndividuals: (status) => `개인 ID를 불러오지 못했습니다: HTTP ${status}`,
    privateAccessRequired: "비공개 코호트 데이터를 보려면 K-PREDICT 접근 코드를 입력하세요.",
    privateAccessPrompt: "K-PREDICT 접근 코드",
    privateAccessFailed: "K-PREDICT 접근 코드가 올바르지 않습니다.",
    restrictedCohort: "제한된 코호트",
    kpredictAccessTitle: "K-PREDICT 접근",
    kpredictAccessSubtitle: "K-PREDICT 또는 관리자 접근 코드를 입력하세요.",
    accessCode: "접근 코드",
    accessCodePlaceholder: "접근 코드 입력",
    accessCodeRequired: "접근 코드를 입력하세요.",
    checkingAccessCode: "접근 코드를 확인하는 중...",
    continueAction: "계속",
    closeKpredictAccess: "K-PREDICT 접근 창 닫기",
    findIndividualsByRisk: "질환별 위험도 검색",
    clearRiskFilter: "위험도 검색 조건 지우기",
    cohortFinder: "코호트 검색",
    riskFilterTitle: "질환별 위험도 검색",
    riskFilterSubtitle: "질환별 백분위를 기준으로 K-PREDICT 코호트에서 개인을 검색합니다.",
    closeRiskFilter: "검색 창 닫기",
    diseaseModel: "질환 모델",
    percentileBand: "백분위 구간",
    resultOrder: "결과 정렬",
    riskBandTop1: "상위 1%",
    riskBandTop5: "상위 5%",
    riskBandTop10: "상위 10%",
    riskBandTop25: "상위 25%",
    riskBandMiddle50: "중간 50%",
    riskBandBottom25: "하위 25%",
    riskBandBottom10: "하위 10%",
    riskBandBottom5: "하위 5%",
    riskBandBottom1: "하위 1%",
    riskBandAll: "전체 대상자",
    highestFirst: "백분위 높은 순",
    lowestFirst: "백분위 낮은 순",
    cancel: "취소",
    applyRiskFilter: "검색",
    applyingRiskFilter: "전체 코호트에서 검색하는 중...",
    riskFilterFailed: "위험도 검색 결과를 불러오지 못했습니다.",
    riskFilterNote: "백분위는 이 질환 모델의 적용 대상인 K-PREDICT 참조 집단에서의 상대적 위치이며, 실제 발병 확률을 의미하지 않습니다.",
    riskFilterSummary: (disease, band, count) => `${disease} · ${band} · ${count}명`,
    riskFilterResult: (count, applicable) => `대상자 ${applicable}명 중 ${count}명이 조건에 맞습니다.`,
    riskFilteredIndividualCount: (matches, total, shown = matches) => {
      const narrowed = matches < total ? `위험도 조건에 맞는 ${total}명 중 ${matches}명 검색됨` : `위험도 조건에 맞는 ${total}명`;
      return shown < matches ? `${narrowed} · 처음 ${shown}명 표시` : narrowed;
    },
    individualFindings: "개인별 소견",
    rareVariantOverview: "희귀 변이",
    loadingRareVariants: "희귀 변이를 불러오는 중...",
    rareOverviewLoadFailed: "희귀 변이 소견을 불러올 수 없습니다.",
    rareOverviewNoFindings: "이 개인에게 등록된 희귀 변이 소견이 없습니다.",
    rareOverviewSelectIndividual: "희귀 변이 소견을 보려면 개인을 선택하세요.",
    rareOverviewGeneCount: (count) => `유전자 ${count}개`,
    rareOverviewAlertGenes: (count) => `주의 소견 포함 ${count}개`,
    rareOverviewCarrierGenes: (count) => `보인자 소견 포함 ${count}개`,
    rareOverviewVariantCount: (count) => `고유 변이 ${count}개`,
    rareAlertHelpLabel: "주의 소견이란?",
    rareAlertHelp: "주의 소견은 데이터 제공자가 우선적으로 검토하도록 지정한 항목입니다. 질환 진단을 의미하지 않습니다.",
    rareCarrierHelpLabel: "보인자 소견이란?",
    rareCarrierHelp: "보인자 소견은 열성 질환과 관련된 이형접합 변이입니다. 일반적으로 해당 질환의 발병이 아니라 보인자 상태를 의미합니다.",
    rareAlert: "주의",
    rareCarrier: "보인자",
    rareFinding: "소견",
    rareOther: "기타",
    viewRareDetails: "희귀 변이 상세 보기",
    rarePanelAssignments: (count) => `질환 패널 ${count}개`,
    diseaseLinkedRareFindings: "질환 연계 희귀 변이 소견",
    cardAlertCount: (count) => `주의 소견 ${count}건`,
    cardCarrierCount: (count) => `보인자 소견 ${count}건`,
    separateRareEvidence: "별도의 희귀 변이 근거",
    cardPanelAlertCount: (count) => `희귀 변이 패널 · 주의 소견 ${count}건`,
    cardPanelCarrierCount: (count) => `희귀 변이 패널 · 보인자 소견 ${count}건`,
    rareEvidenceWithoutPrsHelp: "원자료의 질환 패널 소견은 적용할 수 없는 PRS 모델과 별개의 근거이며 PRS 백분위를 제공하지 않습니다.",
    geneHeatmap: "유전자 히트맵",
    exploratoryAnalysis: "질환 간 비교",
    geneHeatmapTitle: "질환별 유전자 기여도 비교",
    closeGeneHeatmap: "유전자 기여도 비교 닫기",
    geneHeatmapLoading: "질환별 유전자 기여도를 비교하는 중...",
    geneHeatmapFailed: "유전자 기여도 비교 결과를 불러오지 못했습니다.",
    geneHeatmapPlotlyUnavailable: "유전자 히트맵을 표시할 수 없습니다.",
    geneHeatmapScale: "표준화 유전자 기여도 (표준편차)",
    geneHeatmapMissingValue: "표준화 기여도 값 없음",
    geneHeatmapSubtitle: (pid, count) => `${pid} · 분석 대상 질환 모델 ${count}개`,
    geneHeatmapMethod: (fraction, minimum, maximum, candidates, unavailable) => {
      const excluded = unavailable ? ` 이 개인에게 적용되지 않는 질환 모델 ${unavailable}개는 분석에서 제외했습니다.` : "";
      return `표준화 기여도의 절댓값이 최소 ${minimum}개 질환에서 상위 ${fraction}%에 드는 유전자를 포함합니다. 조건을 충족한 ${candidates}개 유전자 중 여러 질환에서 공통으로 나타나고 기여도가 큰 순서로 최대 ${maximum}개를 표시합니다. 각 셀은 유전자 기여도를 집단 분산의 제곱근으로 나눈 값입니다. 양수는 PRS를 높이고 음수는 낮춥니다. 극단값 때문에 나머지 패턴이 흐려지지 않도록 색상 범위를 절댓값의 95백분위수에서 제한했으며, 정확한 값은 마우스를 올려 확인할 수 있습니다. 회색 셀은 해당 유전자-질환 조합의 표준화 기여도 값이 없음을 뜻하며 0으로 해석해서는 안 됩니다.${excluded} 이 결과는 질환 간 공통 기여 패턴을 탐색하기 위한 것으로, 생물학적 상호작용을 입증하지 않으며 여러 질환을 하나의 위험 점수로 합산하지 않습니다.`;
    },
    geneComparisonView: "유전자 비교 보기",
    individualGeneProfile: "선택한 개인",
    populationArchitecture: "집단 유전자 구조",
    prototype: "프로토타입",
    architectureThreshold: "고분산 기준",
    architectureMinimumDiseases: "최소 공통 질환 수",
    topTwoPointFivePercent: "상위 2.5%",
    topOnePercent: "상위 1%",
    topHalfPercent: "상위 0.5%",
    twoDiseases: "질환 2개",
    threeDiseases: "질환 3개",
    fourDiseases: "질환 4개",
    updateComparison: "비교 업데이트",
    populationArchitectureLoading: "질환 모델별 집단 유전자 구조를 비교하는 중...",
    populationArchitectureFailed: "집단 유전자 구조 비교 결과를 불러오지 못했습니다.",
    populationArchitectureScale: "집단 분산 백분위",
    populationRawVariance: "원 집단 분산",
    populationArchitectureMissing: "이 질환 모델에 해당 유전자 없음",
    populationArchitectureSubtitle: (count) => `K-PREDICT 질환 모델 ${count}개`,
    populationArchitectureMethod: (threshold, minimum, shown, candidates) => `이 프로토타입은 각 유전자의 집단 기여도 분산을 동일한 질환 모델 내 다른 유전자와 비교합니다. 최소 ${minimum}개 질환에서 상위 ${(100 - threshold).toFixed(threshold % 1 ? 1 : 0)}%에 포함된 유전자 ${candidates}개 중 ${shown}개를 표시합니다. 값이 99라면 해당 질환 모델 유전자의 약 99%보다 기여도 분산이 크다는 뜻입니다. 이는 제공된 PRS 모델의 구조를 비교한 결과이며, 유전자가 질환을 유발하거나 질환 간 생물학적 연관성을 만든다는 근거는 아닙니다.`,
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
  coronary_artery_disease: "관상동맥질환",
  myocardial_infarction: "심근경색",
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

function clinvarSearchUrl(value) {
  const hgvs = String(value || "").trim();
  return hgvs
    ? `https://www.ncbi.nlm.nih.gov/clinvar/?term=${encodeURIComponent(hgvs)}`
    : "";
}

function clinvarVariantLink(hgvs, label) {
  const url = clinvarSearchUrl(hgvs);
  if (!url) return escapeHtml(label);
  return `<a class="clinvar-variant-link" href="${url}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer" aria-label="${escapeHtml(`${label} — ClinVar`)}">
    <span>${escapeHtml(label)}</span>
    <span class="material-symbols-outlined" aria-hidden="true">open_in_new</span>
    <span class="clinvar-variant-link__source">ClinVar</span>
  </a>`;
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
  if (
    selectedCohortSlug === "kpredict"
    && card.enabled
    && !card.available_for_individual
  ) {
    return t("prsNotApplicable");
  }
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

function updateOverviewPresentation() {
  const isPublicSingleDisease = selectedCohortSlug === "1000_genomes";
  const cohortAnalysisLink = $("cohort-analysis-link");
  if (cohortAnalysisLink) {
    cohortAnalysisLink.hidden = selectedCohortSlug !== "kpredict";
  }
  setText(
    "disease-grid-title",
    t(isPublicSingleDisease ? "singleDiseaseRiskOverview" : "riskOverview"),
  );
  document.querySelector(".disease-panel")?.classList.toggle(
    "is-single-disease-overview",
    isPublicSingleDisease,
  );
}

function applyLanguage(language) {
  currentLanguage = language === "ko" ? "ko" : "en";
  savePreference(LANGUAGE_PREFERENCE_KEY, currentLanguage);
  updateStaticText();

  if (cohortsLoaded) {
    renderCohorts();
  } else {
    setCohortSelectMessage(t("loadingCohorts"));
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
  updateOverviewPresentation();
  populateRiskFilterDiseases();
  renderActiveRiskFilter();
  if (rareOverviewData) renderRareOverview(rareOverviewData);
  if (isGeneHeatmapOpen() && geneHeatmapData) renderGeneHeatmap(geneHeatmapData);
  if (isGeneHeatmapOpen() && populationGeneArchitectureData) {
    renderPopulationGeneArchitecture(populationGeneArchitectureData);
  }
  if (isGeneHeatmapOpen()) syncGeneComparisonView();
  window.XPRSRareVariantDrawer?.refresh({
    language: currentLanguage,
    diseaseLabel: rareDetailDiseaseName,
  });
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
  if (isGeneHeatmapOpen() && geneHeatmapData) renderGeneHeatmap(geneHeatmapData);
  if (isGeneHeatmapOpen() && populationGeneArchitectureData) {
    renderPopulationGeneArchitecture(populationGeneArchitectureData);
  }
}

function toggleTheme() {
  applyTheme(currentTheme === "dark" ? "light" : "dark");
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function fetchJSONWithNetworkRetry(url, options = {}, retryDelays = [0]) {
  let lastError = null;
  for (let attempt = 0; attempt < retryDelays.length; attempt += 1) {
    const delay = retryDelays[attempt];
    if (delay) await wait(delay);
    try {
      const response = await fetch(url, options);
      if (!response.ok) {
        const detail = await response.text();
        const error = new Error(`${response.status} ${response.statusText}: ${detail}`);
        error.isHttpError = true;
        throw error;
      }
      return await response.json();
    } catch (error) {
      lastError = error;
      // These overview requests are read-only. Retry only interrupted browser
      // connections; HTTP responses represent real application errors.
      if (error?.isHttpError || !(error instanceof TypeError) || attempt + 1 >= retryDelays.length) {
        throw error;
      }
    }
  }
  throw lastError || new Error("Request failed");
}

async function postJSON(url, payload, retryDelays = [0]) {
  return fetchJSONWithNetworkRetry(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, retryDelays);
}

function renderIndividuals(individuals, { selectFallback = false } = {}) {
  const select = $("individual-id");
  if (!select) return;
  const preferred = selectedIndividualId || select.value || "";
  let visible = individuals.slice(0, INDIVIDUAL_SEARCH_LIMIT);
  if (preferred && individuals.includes(preferred) && !visible.includes(preferred)) {
    visible = [preferred, ...visible.slice(0, INDIVIDUAL_SEARCH_LIMIT - 1)];
  }
  const nextSelection = visible.includes(preferred)
    ? preferred
    : (selectFallback ? visible[0] || "" : "");
  const renderKey = `${nextSelection}\n${visible.join("\n")}`;
  if (renderKey !== renderedIndividualKey) {
    const fragment = document.createDocumentFragment();
    visible.forEach((pid) => {
      const option = document.createElement("option");
      option.value = pid;
      const percentile = riskPercentileById.get(pid);
      option.textContent = Number.isFinite(percentile)
        ? `${pid} · ${percentile.toFixed(1)}%`
        : pid;
      fragment.appendChild(option);
    });
    select.replaceChildren(fragment);
    if (nextSelection) {
      select.value = nextSelection;
    } else {
      select.selectedIndex = -1;
    }
    renderedIndividualKey = renderKey;
  }
  if (selectFallback && nextSelection) {
    selectedIndividualId = nextSelection;
    if (selectedCohortSlug === "1000_genomes") {
      savePreference(INDIVIDUAL_PREFERENCE_KEY, selectedIndividualId);
    }
  }
  if (!individuals.length && selectFallback) {
    selectedIndividualId = "";
  }
  select.disabled = visible.length === 0;
  const search = $("individual-search");
  if (search) search.disabled = allIndividuals.length === 0;
  const riskTotal = riskFilteredIndividuals?.length;
  setText(
    "individual-status",
    riskFilteredIndividuals !== null
      ? t("riskFilteredIndividualCount", individuals.length, riskTotal, visible.length)
      : t("individualCount", individuals.length, visible.length),
  );
}

function currentIndividualPool() {
  return riskFilteredIndividuals === null ? allIndividuals : riskFilteredIndividuals;
}

function rebuildIndividualSearchIndex() {
  individualSearchIndex = currentIndividualPool().map((pid) => ({
    pid,
    searchValue: pid.toLowerCase(),
  }));
}

function filterIndividuals() {
  const term = ($("individual-search")?.value || "").trim().toLowerCase();
  const filtered = term
    ? individualSearchIndex
        .filter((entry) => entry.searchValue.includes(term))
        .map((entry) => entry.pid)
    : currentIndividualPool();
  renderIndividuals(filtered);
}

function scheduleIndividualFilter() {
  window.clearTimeout(individualSearchTimer);
  individualSearchTimer = window.setTimeout(filterIndividuals, INDIVIDUAL_SEARCH_DEBOUNCE_MS);
}

function clearIndividualSearch() {
  window.clearTimeout(individualSearchTimer);
  const input = $("individual-search");
  if (input) input.value = "";
}

function syncRiskFilterAvailability() {
  const tools = $("risk-filter-tools");
  if (!tools) return;
  tools.hidden = selectedCohortSlug !== "kpredict";
}

function populateRiskFilterDiseases() {
  const select = $("risk-filter-disease");
  if (!select) return;
  const preferred = select.value || activeRiskFilter?.disease || "breast_cancer";
  const fragment = document.createDocumentFragment();
  diseases.forEach((disease) => {
    const option = document.createElement("option");
    option.value = disease.slug;
    option.textContent = diseaseDisplayName(disease);
    fragment.appendChild(option);
  });
  select.replaceChildren(fragment);
  if (diseases.some((disease) => disease.slug === preferred)) select.value = preferred;
}

function renderActiveRiskFilter() {
  const active = $("risk-filter-active");
  if (!active) return;
  if (!activeRiskFilter) {
    active.hidden = true;
    setText("risk-filter-active-text", "");
    return;
  }
  const disease = diseases.find((item) => item.slug === activeRiskFilter.disease);
  const diseaseName = disease ? diseaseDisplayName(disease) : activeRiskFilter.disease;
  const bandName = t(RISK_BAND_TEXT_KEYS[activeRiskFilter.band] || "riskBandAll");
  setText(
    "risk-filter-active-text",
    t("riskFilterSummary", diseaseName, bandName, activeRiskFilter.matchingCount),
  );
  active.hidden = false;
}

function openRiskFilter() {
  if (selectedCohortSlug !== "kpredict") return;
  populateRiskFilterDiseases();
  if (activeRiskFilter) {
    $("risk-filter-disease").value = activeRiskFilter.disease;
    $("risk-filter-band").value = activeRiskFilter.band;
    $("risk-filter-order").value = activeRiskFilter.order;
    setText(
      "risk-filter-status",
      t("riskFilterResult", activeRiskFilter.matchingCount, activeRiskFilter.applicableCount),
    );
  } else {
    setText("risk-filter-status", "");
  }
  $("risk-filter-status")?.classList.remove("is-error");
  const overlay = $("risk-filter-overlay");
  if (overlay) overlay.hidden = false;
  $("risk-filter-disease")?.focus();
}

function closeRiskFilter({ cancelRequest = true } = {}) {
  if (cancelRequest) riskFilterRequestId += 1;
  const overlay = $("risk-filter-overlay");
  const wasOpen = Boolean(overlay && !overlay.hidden);
  if (overlay) overlay.hidden = true;
  if (wasOpen) $("risk-filter-open-btn")?.focus();
}

async function applyRiskFilter(event) {
  event?.preventDefault();
  if (selectedCohortSlug !== "kpredict") return;
  const disease = $("risk-filter-disease")?.value || "breast_cancer";
  const band = $("risk-filter-band")?.value || "top_10";
  const order = $("risk-filter-order")?.value || "desc";
  const bounds = RISK_BANDS[band] || RISK_BANDS.top_10;
  const status = $("risk-filter-status");
  const applyButton = $("risk-filter-apply-btn");
  if (status) {
    status.textContent = t("applyingRiskFilter");
    status.classList.remove("is-error");
  }
  if (applyButton) applyButton.disabled = true;
  const requestId = ++riskFilterRequestId;
  const params = new URLSearchParams({
    disease,
    percentile_min: String(bounds.minimum),
    percentile_max: String(bounds.maximum),
    order,
    limit: "5000",
  });
  try {
    const response = await fetch(`/api/kpredict/individual-risk-filter?${params.toString()}`);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `${t("riskFilterFailed")} (HTTP ${response.status})`);
    }
    const data = await response.json();
    if (requestId !== riskFilterRequestId) return;
    const results = Array.isArray(data.results) ? data.results : [];
    riskFilteredIndividuals = results.map((result) => result.individual_id);
    riskPercentileById = new Map(
      results.map((result) => [result.individual_id, Number(result.percentile)]),
    );
    activeRiskFilter = {
      disease,
      band,
      order,
      matchingCount: Number(data.matching_count) || 0,
      applicableCount: Number(data.applicable_count) || 0,
    };
    clearIndividualSearch();
    rebuildIndividualSearchIndex();
    renderedIndividualKey = "";
    renderIndividuals(riskFilteredIndividuals, { selectFallback: true });
    renderActiveRiskFilter();
    syncCrossDiseaseHeatmapButton();
    if (applyButton) applyButton.disabled = false;
    closeRiskFilter({ cancelRequest: false });
    await loadDiseaseOverview();
  } catch (error) {
    if (requestId !== riskFilterRequestId) return;
    if (status) {
      status.textContent = error.message || t("riskFilterFailed");
      status.classList.add("is-error");
    }
  } finally {
    if (requestId === riskFilterRequestId && applyButton) applyButton.disabled = false;
  }
}

function clearRiskFilter({ refreshOverview = true, render = true } = {}) {
  riskFilterRequestId += 1;
  riskFilteredIndividuals = null;
  riskPercentileById = new Map();
  activeRiskFilter = null;
  clearIndividualSearch();
  rebuildIndividualSearchIndex();
  if (render) {
    renderedIndividualKey = "";
    renderIndividuals(allIndividuals, { selectFallback: true });
  }
  renderActiveRiskFilter();
  syncCrossDiseaseHeatmapButton();
  if (refreshOverview) loadDiseaseOverview();
}

function syncRareOverviewAvailability() {
  const panel = $("rare-overview-panel");
  const layout = document.querySelector(".overview-layout");
  const visible = selectedCohortSlug === "kpredict";
  if (panel) panel.hidden = !visible;
  layout?.classList.toggle("has-rare-pane", visible);
}

function rareOverviewDiseaseName(disease) {
  if (currentLanguage === "ko") {
    return DISEASE_NAMES_KO[disease.slug] || disease.display_name || disease.slug;
  }
  return disease.display_name || disease.slug;
}

function rareDetailDiseaseName(slug, fallback = "") {
  if (currentLanguage === "ko") {
    return DISEASE_NAMES_KO[slug] || fallback || slug;
  }
  return fallback || slug;
}

function openRareOverviewDetail(index) {
  const variants = Array.isArray(rareOverviewData?.variants) ? rareOverviewData.variants : [];
  const item = variants[Number(index)];
  if (!item) return;
  window.XPRSRareVariantDrawer?.open(item, {
    language: currentLanguage,
    diseaseLabel: rareDetailDiseaseName,
  });
}

function rareSummaryHelp(labelKey, helpKey) {
  return `
    <button
      class="rare-summary-help"
      type="button"
      aria-label="${escapeHtml(t(labelKey))}"
      aria-controls="rare-summary-tooltip"
      aria-expanded="false"
      data-help-key="${escapeHtml(helpKey)}"
    ><span class="material-symbols-outlined" aria-hidden="true">help</span></button>
  `;
}

function positionRareSummaryTooltip() {
  const tooltip = $("rare-summary-tooltip");
  const button = rareTooltipAnchor;
  if (!tooltip || !button || !button.isConnected || tooltip.hidden) return;

  const edge = 12;
  const gap = 9;
  const buttonRect = button.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();
  const roomBelow = window.innerHeight - buttonRect.bottom;
  const placeAbove = roomBelow < tooltipRect.height + gap + edge
    && buttonRect.top > tooltipRect.height + gap + edge;
  const top = placeAbove
    ? buttonRect.top - tooltipRect.height - gap
    : buttonRect.bottom + gap;
  const preferredLeft = buttonRect.left + (buttonRect.width / 2) - (tooltipRect.width / 2);
  const maximumLeft = Math.max(edge, window.innerWidth - tooltipRect.width - edge);
  const left = Math.min(Math.max(edge, preferredLeft), maximumLeft);
  const arrowLeft = Math.min(
    Math.max(12, buttonRect.left + (buttonRect.width / 2) - left),
    tooltipRect.width - 12,
  );

  tooltip.classList.toggle("is-above", placeAbove);
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${Math.max(edge, top)}px`;
  tooltip.style.setProperty("--rare-tooltip-arrow-left", `${arrowLeft}px`);
}

function showRareSummaryTooltip(button, { pinned = false } = {}) {
  const tooltip = $("rare-summary-tooltip");
  if (!tooltip || !button) return;
  if (rareTooltipPinned && rareTooltipAnchor !== button && !pinned) return;
  if (rareTooltipAnchor && rareTooltipAnchor !== button) {
    rareTooltipAnchor.setAttribute("aria-expanded", "false");
    rareTooltipAnchor.removeAttribute("aria-describedby");
  }
  rareTooltipAnchor = button;
  rareTooltipPinned = pinned;
  tooltip.textContent = t(button.dataset.helpKey);
  tooltip.hidden = false;
  button.setAttribute("aria-expanded", String(pinned));
  button.setAttribute("aria-describedby", "rare-summary-tooltip");
  positionRareSummaryTooltip();
}

function hideRareSummaryTooltip({ force = false } = {}) {
  if (rareTooltipPinned && !force) return;
  const tooltip = $("rare-summary-tooltip");
  if (rareTooltipAnchor) {
    rareTooltipAnchor.setAttribute("aria-expanded", "false");
    rareTooltipAnchor.removeAttribute("aria-describedby");
  }
  if (tooltip) tooltip.hidden = true;
  rareTooltipAnchor = null;
  rareTooltipPinned = false;
}

function bindRareSummaryHelp(summary) {
  summary.querySelectorAll(".rare-summary-help").forEach((button) => {
    button.addEventListener("mouseenter", () => showRareSummaryTooltip(button));
    button.addEventListener("mouseleave", () => hideRareSummaryTooltip());
    button.addEventListener("focus", () => showRareSummaryTooltip(button));
    button.addEventListener("blur", () => hideRareSummaryTooltip());
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      if (rareTooltipPinned && rareTooltipAnchor === button) {
        hideRareSummaryTooltip({ force: true });
      } else {
        showRareSummaryTooltip(button, { pinned: true });
      }
    });
    button.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        hideRareSummaryTooltip({ force: true });
        button.focus();
      }
    });
  });
}

function renderRareOverview(data) {
  const content = $("rare-overview-content");
  const summary = $("rare-overview-summary");
  if (!content || !summary) return;
  hideRareSummaryTooltip({ force: true });
  if (!data) {
    summary.hidden = true;
    setText("rare-overview-subtitle", "");
    content.innerHTML = `<div class="rare-overview-state">${escapeHtml(t("rareOverviewSelectIndividual"))}</div>`;
    return;
  }

  const variants = Array.isArray(data.variants) ? data.variants : [];
  const alertGenes = new Set(
    variants
      .filter((item) => item.call === "alert" && item.gene)
      .map((item) => String(item.gene)),
  );
  const carrierGenes = new Set(
    variants
      .filter((item) => item.call === "carrier" && item.gene)
      .map((item) => String(item.gene)),
  );
  const geneCount = Number(data.gene_count) || 0;
  const variantCount = Number(data.variant_count) || 0;
  const summaryMetrics = [
    `<span class="rare-summary-metric is-total">${escapeHtml(t("rareOverviewGeneCount", geneCount))}</span>`,
  ];
  if (alertGenes.size) {
    summaryMetrics.push(`
      <span class="rare-summary-metric is-alert">
        ${escapeHtml(t("rareOverviewAlertGenes", alertGenes.size))}
        ${rareSummaryHelp("rareAlertHelpLabel", "rareAlertHelp")}
      </span>
    `);
  }
  if (carrierGenes.size) {
    summaryMetrics.push(`
      <span class="rare-summary-metric">
        ${escapeHtml(t("rareOverviewCarrierGenes", carrierGenes.size))}
        ${rareSummaryHelp("rareCarrierHelpLabel", "rareCarrierHelp")}
      </span>
    `);
  }
  setText("rare-overview-subtitle", data.individual_id || "");
  summary.innerHTML = `
    <div class="rare-overview-summary__metrics">${summaryMetrics.join('<span class="rare-summary-separator" aria-hidden="true">·</span>')}</div>
    <div class="rare-overview-summary__variants">${escapeHtml(t("rareOverviewVariantCount", variantCount))}</div>
  `;
  bindRareSummaryHelp(summary);
  summary.hidden = false;
  if (!variants.length) {
    content.innerHTML = `<div class="rare-overview-state">${escapeHtml(t("rareOverviewNoFindings"))}</div>`;
    return;
  }

  content.innerHTML = variants.map((item, index) => {
    const call = item.call === "alert"
      ? t("rareAlert")
      : (item.call === "carrier" ? t("rareCarrier") : t("rareFinding"));
    const callClass = item.call === "alert" ? " is-alert" : "";
    const primaryVariant = item.hgvs || item.variant || item.rsid || "—";
    const primaryVariantMarkup = clinvarVariantLink(item.hgvs, primaryVariant);
    const metadata = [];
    if (item.rsid) metadata.push(String(item.rsid));
    if (item.consequence) metadata.push(String(item.consequence).replaceAll("_", " "));
    if (item.clnsig) metadata.push(String(item.clnsig));
    if (Number(item.stars)) metadata.push(`ClinVar ${"★".repeat(Math.min(4, Number(item.stars)))}`);
    if (item.genotype) metadata.push(`GT ${item.genotype}`);
    if (Array.isArray(item.diseases) && item.diseases.length > 1) {
      metadata.push(t("rarePanelAssignments", item.diseases.length));
    }
    const diseaseBadges = (Array.isArray(item.diseases) ? item.diseases : [])
      .map((disease) => `<span class="rare-disease-badge">${escapeHtml(rareOverviewDiseaseName(disease))}</span>`)
      .join("");
    const unassignedBadge = item.unassigned
      ? `<span class="rare-disease-badge is-unassigned">${escapeHtml(t("rareOther"))}</span>`
      : "";
    return `
      <article class="rare-overview-item">
        <div class="rare-overview-item__header">
          <span class="rare-overview-item__gene">${escapeHtml(item.gene || "—")}</span>
          <div class="rare-overview-item__actions">
            <span class="rare-call-badge${callClass}">${escapeHtml(call)}</span>
            <button class="rare-detail-trigger" type="button" data-rare-detail-index="${index}" aria-label="${escapeHtml(t("viewRareDetails"))}" title="${escapeHtml(t("viewRareDetails"))}">
              <span class="material-symbols-outlined" aria-hidden="true">info</span>
            </button>
          </div>
        </div>
        <div class="rare-overview-item__variant">${primaryVariantMarkup}</div>
        ${metadata.length ? `<div class="rare-overview-item__meta">${metadata.map(escapeHtml).join(" · ")}</div>` : ""}
        <div class="rare-disease-badges">${diseaseBadges}${unassignedBadge}</div>
      </article>
    `;
  }).join("");
}

async function loadRareOverview(individualId) {
  const content = $("rare-overview-content");
  const summary = $("rare-overview-summary");
  if (selectedCohortSlug !== "kpredict" || !content || !summary) return;
  if (!individualId) {
    rareOverviewData = null;
    renderRareOverview(null);
    return;
  }
  const requestId = ++rareOverviewRequestId;
  summary.hidden = true;
  setText("rare-overview-subtitle", individualId);
  content.innerHTML = `<div class="rare-overview-state">${escapeHtml(t("loadingRareVariants"))}</div>`;
  const params = new URLSearchParams({ individual_id: individualId });
  try {
    const data = await fetchJSONWithNetworkRetry(
      `/api/kpredict/rare-findings-overview?${params.toString()}`,
      {},
      OVERVIEW_NETWORK_RETRY_DELAYS_MS,
    );
    if (requestId !== rareOverviewRequestId || individualId !== selectedIndividualId) return;
    rareOverviewData = data;
    renderRareOverview(data);
  } catch (error) {
    if (requestId !== rareOverviewRequestId) return;
    rareOverviewData = null;
    summary.hidden = true;
    const message = error instanceof TypeError
      ? t("overviewConnectionFailed")
      : (error.message || t("rareOverviewLoadFailed"));
    content.innerHTML = `<div class="rare-overview-state">${escapeHtml(message)}</div>`;
  }
}

function renderCohorts() {
  const select = $("cohort-select");
  if (!select) return;
  select.disabled = false;
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
  if (!cohort) return;
  updateOverviewPresentation();
}

function setCohortSelectMessage(message) {
  const select = $("cohort-select");
  if (!select) return;
  const option = document.createElement("option");
  option.textContent = message;
  option.selected = true;
  select.replaceChildren(option);
  select.disabled = true;
}

function densityCardShell(card) {
  const isAvailable = Boolean(card.enabled && card.available_for_individual && card.density);
  const isPrsInapplicable = Boolean(
    selectedCohortSlug === "kpredict"
    && card.enabled
    && !card.available_for_individual
  );
  const tag = isAvailable ? "button" : "div";
  const disabledClass = isAvailable ? "" : " is-disabled";
  const status = isAvailable
    ? t("available")
    : (isPrsInapplicable ? t("prsUnavailableStatus") : t("unavailable"));
  const displayName = diseaseDisplayName(card);
  const reason = unavailableReason(card);
  const panelFindings = card.panel_findings || {};
  const alertCount = Number(panelFindings.alert_count) || 0;
  const carrierCount = Number(panelFindings.carrier_count) || 0;
  const rareBadges = [];
  if (alertCount) {
    const label = isPrsInapplicable
      ? t("cardPanelAlertCount", alertCount)
      : t("cardAlertCount", alertCount);
    rareBadges.push(`
      <span class="card-rare-badge${isPrsInapplicable ? " is-prs-separate" : " is-alert"}"${isPrsInapplicable ? ` title="${escapeHtml(t("rareEvidenceWithoutPrsHelp"))}"` : ""}>
        <span class="material-symbols-outlined" aria-hidden="true">${isPrsInapplicable ? "genetics" : "priority_high"}</span>
        ${escapeHtml(label)}
      </span>
    `);
  }
  if (carrierCount) {
    const label = isPrsInapplicable
      ? t("cardPanelCarrierCount", carrierCount)
      : t("cardCarrierCount", carrierCount);
    rareBadges.push(`
      <span class="card-rare-badge${isPrsInapplicable ? " is-prs-separate" : ""}"${isPrsInapplicable ? ` title="${escapeHtml(t("rareEvidenceWithoutPrsHelp"))}"` : ""}>
        <span class="material-symbols-outlined" aria-hidden="true">genetics</span>
        ${escapeHtml(label)}
      </span>
    `);
  }
  const rareEvidence = rareBadges.length
    ? `<div class="card-rare-evidence${isPrsInapplicable ? " is-prs-separate" : ""}" aria-label="${escapeHtml(t("diseaseLinkedRareFindings"))}">${isPrsInapplicable ? `<span class="card-rare-evidence__label">${escapeHtml(t("separateRareEvidence"))}</span>` : ""}${rareBadges.join("")}</div>`
    : "";
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
      ${rareEvidence}
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

function mixRgb(left, right, amount) {
  const ratio = Math.max(0, Math.min(1, amount));
  return left.map((value, index) => Math.round(value + ((right[index] - value) * ratio)));
}

function percentileTint(percentile, darkTheme = false) {
  const value = Math.max(0, Math.min(1, Number(percentile) || 0));
  const low = darkTheme ? [91, 169, 224] : [42, 123, 181];
  const middle = darkTheme ? [151, 164, 176] : [111, 127, 141];
  const high = darkTheme ? [244, 125, 115] : [196, 67, 58];
  const rgb = value <= 0.5
    ? mixRgb(low, middle, value / 0.5)
    : mixRgb(middle, high, (value - 0.5) / 0.5);
  return {
    fill: `rgba(${rgb.join(", ")}, ${darkTheme ? 0.26 : 0.18})`,
    background: `rgba(${rgb.join(", ")}, ${darkTheme ? 0.09 : 0.06})`,
  };
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
  const percentile = Math.max(0, Math.min(1, Number(density?.percentile) || 0));
  const tint = percentileTint(percentile, darkTheme);
  el.setAttribute("aria-label", `${diseaseDisplayName(card)}: ${t("percentile")} ${(percentile * 100).toFixed(1)}%`);
  const trace = {
    type: "scatter",
    mode: "lines",
    x,
    y,
    line: { color: darkTheme ? "#7bb2f6" : "#27609d", width: 2.2 },
    fill: "tozeroy",
    fillcolor: tint.fill,
    hoverinfo: "skip",
  };

  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: tint.background,
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

function isGeneHeatmapOpen() {
  return !$('gene-heatmap-overlay')?.hidden;
}

function syncCrossDiseaseHeatmapButton() {
  const button = $("cross-disease-heatmap-btn");
  if (!button) return;
  button.hidden = selectedCohortSlug !== "kpredict" || !selectedIndividualId;
}

function localizedHeatmapDiseaseName(disease) {
  if (currentLanguage === "ko") {
    return DISEASE_NAMES_KO[disease.slug] || disease.display_name || disease.slug;
  }
  return disease.display_name || disease.slug;
}

function renderGeneHeatmap(data) {
  const plot = $("gene-heatmap-plot");
  const status = $("gene-heatmap-status");
  const note = $("gene-heatmap-note");
  if (!plot || !status || !note) return;
  if (!window.Plotly) {
    status.textContent = t("geneHeatmapPlotlyUnavailable");
    status.classList.add("is-error");
    status.hidden = false;
    plot.hidden = true;
    note.hidden = true;
    return;
  }

  const diseases = Array.isArray(data.diseases) ? data.diseases : [];
  const genes = Array.isArray(data.genes) ? data.genes : [];
  const geneMetrics = Array.isArray(data.gene_metrics) ? data.gene_metrics : [];
  const values = Array.isArray(data.values) ? data.values : [];
  const selection = data.selection || {};
  const unavailable = Array.isArray(data.unavailable_diseases)
    ? data.unavailable_diseases.length
    : 0;
  const diseaseLabels = diseases.map(localizedHeatmapDiseaseName);
  const geneLabels = genes.map((gene, index) => {
    const metric = geneMetrics[index] || {};
    const support = Number(metric.qualifying_disease_count) || 0;
    return support ? `${gene} · ${support}/${diseases.length}` : gene;
  });
  const darkTheme = currentTheme === "dark";
  const colorLimit = Math.max(2, Number(data.color_limit) || 2);
  const height = Math.max(500, genes.length * 27 + 165);
  plot.style.height = `${height}px`;
  status.hidden = true;
  status.classList.remove("is-error");
  plot.hidden = false;
  note.textContent = t(
    "geneHeatmapMethod",
    ((Number(selection.top_fraction) || 0.0025) * 100).toFixed(2),
    Number(selection.minimum_qualifying_diseases) || 3,
    Number(selection.maximum_genes) || 20,
    Number(selection.candidate_count) || genes.length,
    unavailable,
  );
  note.hidden = false;
  setText("gene-heatmap-subtitle", t("geneHeatmapSubtitle", data.individual_id, diseases.length));

  const missingValues = values.map((row) => row.map((value) => (
    value === null || value === undefined || !Number.isFinite(Number(value)) ? 1 : null
  )));
  const hoverLabels = values.map((row) => row.map((value) => (
    value === null || value === undefined || !Number.isFinite(Number(value))
      ? t("geneHeatmapMissingValue")
      : `${t("geneHeatmapScale")}: ${Number(value).toFixed(2)}`
  )));
  const hasMissingValues = missingValues.some((row) => row.some((value) => value === 1));
  const missingTrace = {
    type: "heatmap",
    x: diseaseLabels,
    y: geneLabels,
    z: missingValues,
    text: hoverLabels,
    zmin: 0,
    zmax: 1,
    colorscale: [[0, darkTheme ? "#4a535c" : "#c9cfd6"], [1, darkTheme ? "#4a535c" : "#c9cfd6"]],
    showscale: false,
    xgap: 1,
    ygap: 1,
    hovertemplate: "<b>%{y}</b><br>%{x}<br>%{text}<extra></extra>",
  };
  const trace = {
    type: "heatmap",
    x: diseaseLabels,
    y: geneLabels,
    z: values,
    text: hoverLabels,
    zmin: -colorLimit,
    zmid: 0,
    zmax: colorLimit,
    xgap: 1,
    ygap: 1,
    colorscale: darkTheme
      ? [[0, "#4f92d1"], [0.5, "#2b333b"], [1, "#ef6a6a"]]
      : [[0, "#2166ac"], [0.5, "#edf0f3"], [1, "#b2182b"]],
    colorbar: {
      title: { text: t("geneHeatmapScale"), side: "right", font: { size: 11 } },
      thickness: 14,
      len: 0.82,
    },
    hovertemplate: "<b>%{y}</b><br>%{x}<br>%{text}<extra></extra>",
  };
  const layout = {
    height,
    autosize: true,
    margin: { l: 125, r: 105, t: 18, b: 120 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Inter, sans-serif", color: darkTheme ? "#dee4ea" : "#1f2933" },
    xaxis: {
      fixedrange: true,
      tickangle: -32,
      tickfont: { size: 11 },
      side: "bottom",
    },
    yaxis: {
      fixedrange: true,
      autorange: "reversed",
      tickfont: { size: 11 },
    },
  };
  const traces = hasMissingValues ? [missingTrace, trace] : [trace];
  window.Plotly.react(plot, traces, layout, {
    displayModeBar: false,
    displaylogo: false,
    responsive: true,
    scrollZoom: false,
    doubleClick: false,
  });
}

function syncGeneComparisonView() {
  const isPopulation = activeGeneComparisonView === "population";
  const individualTab = $("individual-heatmap-tab");
  const populationTab = $("population-architecture-tab");
  const individualPanel = $("individual-heatmap-panel");
  const populationPanel = $("population-architecture-panel");
  if (!individualTab || !populationTab || !individualPanel || !populationPanel) return;

  individualTab.classList.toggle("is-active", !isPopulation);
  populationTab.classList.toggle("is-active", isPopulation);
  individualTab.setAttribute("aria-selected", String(!isPopulation));
  populationTab.setAttribute("aria-selected", String(isPopulation));
  individualPanel.hidden = isPopulation;
  populationPanel.hidden = !isPopulation;
  setText(
    "gene-heatmap-title",
    isPopulation ? t("populationArchitecture") : t("geneHeatmapTitle"),
  );
  if (isPopulation) {
    const count = populationGeneArchitectureData?.diseases?.length || diseases.length;
    setText("gene-heatmap-subtitle", t("populationArchitectureSubtitle", count));
  } else if (geneHeatmapData) {
    setText(
      "gene-heatmap-subtitle",
      t("geneHeatmapSubtitle", geneHeatmapData.individual_id, geneHeatmapData.diseases.length),
    );
  }
}

function renderPopulationGeneArchitecture(data) {
  const plot = $("population-architecture-plot");
  const status = $("population-architecture-status");
  const note = $("population-architecture-note");
  if (!plot || !status || !note) return;
  if (!window.Plotly) {
    status.textContent = t("geneHeatmapPlotlyUnavailable");
    status.classList.add("is-error");
    status.hidden = false;
    plot.hidden = true;
    note.hidden = true;
    return;
  }

  const diseasesInData = Array.isArray(data.diseases) ? data.diseases : [];
  const genes = Array.isArray(data.genes) ? data.genes : [];
  const values = Array.isArray(data.values) ? data.values : [];
  const rawVariances = Array.isArray(data.raw_variances) ? data.raw_variances : [];
  const metrics = Array.isArray(data.gene_metrics) ? data.gene_metrics : [];
  const selection = data.selection || {};
  const diseaseLabels = diseasesInData.map(localizedHeatmapDiseaseName);
  const geneLabels = genes.map((gene, index) => {
    const support = Number(metrics[index]?.qualifying_disease_count) || 0;
    return `${gene} · ${support}/${diseasesInData.length}`;
  });
  const darkTheme = currentTheme === "dark";
  const height = Math.max(500, genes.length * 27 + 165);
  plot.style.height = `${height}px`;
  status.hidden = true;
  status.classList.remove("is-error");
  plot.hidden = false;
  note.textContent = t(
    "populationArchitectureMethod",
    Number(selection.percentile_threshold) || 99,
    Number(selection.minimum_qualifying_diseases) || 3,
    genes.length,
    Number(selection.candidate_count) || genes.length,
  );
  note.hidden = false;

  const hoverLabels = values.map((row, rowIndex) => row.map((value, columnIndex) => {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) {
      return t("populationArchitectureMissing");
    }
    const raw = Number(rawVariances[rowIndex]?.[columnIndex]);
    const varianceLabel = Number.isFinite(raw) ? raw.toExponential(3) : "—";
    return `${t("populationArchitectureScale")}: ${Number(value).toFixed(2)}<br>${t("populationRawVariance")}: ${varianceLabel}`;
  }));
  const missingValues = values.map((row) => row.map((value) => (
    value === null || value === undefined || !Number.isFinite(Number(value)) ? 1 : null
  )));
  const hasMissing = missingValues.some((row) => row.some((value) => value === 1));
  const missingTrace = {
    type: "heatmap",
    x: diseaseLabels,
    y: geneLabels,
    z: missingValues,
    text: hoverLabels,
    zmin: 0,
    zmax: 1,
    colorscale: [[0, darkTheme ? "#4a535c" : "#c9cfd6"], [1, darkTheme ? "#4a535c" : "#c9cfd6"]],
    showscale: false,
    xgap: 1,
    ygap: 1,
    hovertemplate: "<b>%{y}</b><br>%{x}<br>%{text}<extra></extra>",
  };
  const trace = {
    type: "heatmap",
    x: diseaseLabels,
    y: geneLabels,
    z: values,
    text: hoverLabels,
    zmin: 0,
    zmax: 100,
    colorscale: darkTheme
      ? [[0, "#22282e"], [0.9, "#29343e"], [0.975, "#35688f"], [0.99, "#4b91c6"], [1, "#8bc7ef"]]
      : [[0, "#f3f5f7"], [0.9, "#e8eef4"], [0.975, "#a9cce5"], [0.99, "#4d91c3"], [1, "#174f7a"]],
    colorbar: {
      title: { text: t("populationArchitectureScale"), side: "right", font: { size: 11 } },
      thickness: 14,
      len: 0.82,
      tickvals: [0, 90, 95, 99, 100],
    },
    xgap: 1,
    ygap: 1,
    hovertemplate: "<b>%{y}</b><br>%{x}<br>%{text}<extra></extra>",
  };
  window.Plotly.react(plot, hasMissing ? [missingTrace, trace] : [trace], {
    height,
    autosize: true,
    margin: { l: 125, r: 105, t: 18, b: 120 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Inter, sans-serif", color: darkTheme ? "#dee4ea" : "#1f2933" },
    xaxis: { fixedrange: true, tickangle: -32, tickfont: { size: 11 }, side: "bottom" },
    yaxis: { fixedrange: true, autorange: "reversed", tickfont: { size: 11 } },
  }, {
    displayModeBar: false,
    displaylogo: false,
    responsive: true,
    scrollZoom: false,
    doubleClick: false,
  });
}

async function loadPopulationGeneArchitecture() {
  const status = $("population-architecture-status");
  const plot = $("population-architecture-plot");
  const note = $("population-architecture-note");
  if (!status || !plot || !note || selectedCohortSlug !== "kpredict") return;
  status.hidden = false;
  status.classList.remove("is-error");
  status.textContent = t("populationArchitectureLoading");
  plot.hidden = true;
  note.hidden = true;
  const requestId = ++populationArchitectureRequestId;
  const params = new URLSearchParams({
    percentile_threshold: $("architecture-threshold")?.value || "99",
    min_diseases: $("architecture-min-diseases")?.value || "3",
    max_genes: "24",
  });
  try {
    const response = await fetch(`/api/kpredict/population-gene-architecture?${params.toString()}`);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `${t("populationArchitectureFailed")} (HTTP ${response.status})`);
    }
    const data = await response.json();
    if (requestId !== populationArchitectureRequestId || !isGeneHeatmapOpen()) return;
    populationGeneArchitectureData = data;
    renderPopulationGeneArchitecture(data);
    syncGeneComparisonView();
  } catch (error) {
    if (requestId !== populationArchitectureRequestId || !isGeneHeatmapOpen()) return;
    status.textContent = error.message || t("populationArchitectureFailed");
    status.classList.add("is-error");
  }
}

function selectGeneComparisonView(view) {
  activeGeneComparisonView = view === "population" ? "population" : "individual";
  syncGeneComparisonView();
  if (activeGeneComparisonView === "population") {
    if (populationGeneArchitectureData) {
      renderPopulationGeneArchitecture(populationGeneArchitectureData);
    } else {
      loadPopulationGeneArchitecture();
    }
  } else if (geneHeatmapData) {
    renderGeneHeatmap(geneHeatmapData);
  }
}

async function openGeneHeatmap() {
  const pid = selectedIndividualId || $("individual-id")?.value || "";
  if (selectedCohortSlug !== "kpredict" || !pid) return;
  const overlay = $("gene-heatmap-overlay");
  const status = $("gene-heatmap-status");
  const plot = $("gene-heatmap-plot");
  const note = $("gene-heatmap-note");
  if (!overlay || !status || !plot || !note) return;

  overlay.hidden = false;
  activeGeneComparisonView = "individual";
  syncGeneComparisonView();
  status.hidden = false;
  status.classList.remove("is-error");
  status.textContent = t("geneHeatmapLoading");
  plot.hidden = true;
  note.hidden = true;
  setText("gene-heatmap-subtitle", pid);
  $("gene-heatmap-close-btn")?.focus();
  const requestId = ++geneHeatmapRequestId;
  const params = new URLSearchParams({
    individual_id: pid,
    top_fraction: "0.0025",
    min_diseases: "3",
    max_genes: "20",
  });
  try {
    const response = await fetch(`/api/kpredict/cross-disease-gene-heatmap?${params.toString()}`);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `${t("geneHeatmapFailed")} (HTTP ${response.status})`);
    }
    const data = await response.json();
    if (requestId !== geneHeatmapRequestId || overlay.hidden) return;
    geneHeatmapData = data;
    renderGeneHeatmap(data);
  } catch (error) {
    if (requestId !== geneHeatmapRequestId || overlay.hidden) return;
    status.textContent = error.message || t("geneHeatmapFailed");
    status.classList.add("is-error");
  }
}

function closeGeneHeatmap() {
  geneHeatmapRequestId += 1;
  populationArchitectureRequestId += 1;
  const overlay = $("gene-heatmap-overlay");
  const wasOpen = Boolean(overlay && !overlay.hidden);
  if (overlay) overlay.hidden = true;
  if (wasOpen) $("cross-disease-heatmap-btn")?.focus();
}

function renderDiseaseCards(cards) {
  const grid = $("disease-grid");
  if (!grid) return;
  visibleDiseaseCards = Array.isArray(cards) ? cards : [];
  grid.classList.toggle("is-single-disease", visibleDiseaseCards.length === 1);
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
  populateRiskFilterDiseases();
  updateCohortStatus();
}

async function loadCohorts() {
  const res = await fetch("/api/cohorts");
  if (!res.ok) throw new Error(t("failedToLoadCohorts", res.status));
  const data = await res.json();
  cohorts = Array.isArray(data.cohorts) ? data.cohorts : [];
  const requestedCohort = new URLSearchParams(window.location.search).get("cohort");
  selectedCohortSlug = requestedCohort || data.default_cohort || selectedCohortSlug;
  if (!cohorts.some((cohort) => cohort.slug === selectedCohortSlug)) {
    selectedCohortSlug = data.default_cohort || "1000_genomes";
  }
  cohortsLoaded = true;
  renderCohorts();
}

async function exchangeKpredictTokenFromFragment() {
  const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const token = fragment.get("token");
  if (!token) return;
  const response = await fetch("/api/kpredict/access", {
    method: "POST",
    headers: { "X-XPRS-KPREDICT-Token": token },
  });
  const url = new URL(window.location.href);
  url.searchParams.set("cohort", "kpredict");
  url.hash = "";
  window.history.replaceState({}, "", `${url.pathname}${url.search}`);
  return response.ok;
}

async function loadIndividuals() {
  const params = new URLSearchParams({ cohort: selectedCohortSlug });
  const res = await fetch(`/api/individuals?${params.toString()}`);
  if (!res.ok) throw new Error(t("failedToLoadIndividuals", res.status));
  const data = await res.json();
  const cohort = getSelectedCohort();
  if (data.enabled === false && cohort?.access === "private") {
    selectedIndividualId = "";
    allIndividuals = [];
    individualSearchIndex = [];
    individualsLoaded = false;
    renderedIndividualKey = "";
    const select = $("individual-id");
    if (select) {
      select.replaceChildren();
      select.disabled = true;
    }
    const search = $("individual-search");
    if (search) search.disabled = true;
    setText("individual-status", "");
    syncCrossDiseaseHeatmapButton();
    syncRiskFilterAvailability();
    syncRareOverviewAvailability();
    requestPrivateCohortAccess();
    return;
  }
  allIndividuals = Array.isArray(data.individuals) ? data.individuals : [];
  rebuildIndividualSearchIndex();
  individualsLoaded = true;
  renderedIndividualKey = "";
  renderIndividuals(allIndividuals, { selectFallback: true });
  syncCrossDiseaseHeatmapButton();
  syncRiskFilterAvailability();
  syncRareOverviewAvailability();
}

function setPrivateAccessStatus(message = "", isError = false) {
  const status = $("kpredict-access-status");
  if (!status) return;
  status.textContent = message;
  status.classList.toggle("is-error", Boolean(isError));
}

function requestPrivateCohortAccess() {
  if (privateAccessPromptShown) return false;
  privateAccessPromptShown = true;
  const overlay = $("kpredict-access-overlay");
  const input = $("kpredict-access-code");
  if (input) input.value = "";
  setPrivateAccessStatus();
  if (overlay) overlay.hidden = false;
  window.setTimeout(() => input?.focus(), 0);
  return true;
}

function closePrivateCohortAccess({ returnToPublic = false } = {}) {
  const overlay = $("kpredict-access-overlay");
  if (overlay) overlay.hidden = true;
  privateAccessPromptShown = false;
  setPrivateAccessStatus();
  if (!returnToPublic || selectedCohortSlug !== "kpredict") return;
  const publicCohort = cohorts.find((cohort) => cohort.access !== "private");
  const cohortSelect = $("cohort-select");
  if (!publicCohort || !cohortSelect) return;
  cohortSelect.value = publicCohort.slug;
  cohortSelect.dispatchEvent(new Event("change"));
}

async function submitPrivateCohortAccess(event) {
  event?.preventDefault();
  const input = $("kpredict-access-code");
  const submit = $("kpredict-access-submit-btn");
  const token = (input?.value || "").trim();
  if (!token) {
    setPrivateAccessStatus(t("accessCodeRequired"), true);
    input?.focus();
    return false;
  }
  if (submit) submit.disabled = true;
  if (input) input.disabled = true;
  setPrivateAccessStatus(t("checkingAccessCode"));
  try {
    const response = await fetch("/api/kpredict/access", {
      method: "POST",
      headers: { "X-XPRS-KPREDICT-Token": token },
    });
    if (!response.ok) {
      setPrivateAccessStatus(t("privateAccessFailed"), true);
      input?.focus();
      return false;
    }
    const url = new URL(window.location.href);
    url.searchParams.set("cohort", "kpredict");
    url.hash = "";
    window.location.replace(`${url.pathname}${url.search}`);
    return true;
  } catch (_error) {
    setPrivateAccessStatus(t("privateAccessFailed"), true);
    input?.focus();
    return false;
  } finally {
    if (submit) submit.disabled = false;
    if (input) input.disabled = false;
    if ($("kpredict-access-status")?.classList.contains("is-error")) {
      window.setTimeout(() => input?.focus(), 0);
    }
  }
}

async function loadDiseaseOverview() {
  const requestId = ++diseaseOverviewRequestId;
  const pid = selectedIndividualId || $("individual-id")?.value || "";
  if (!pid) {
    syncCrossDiseaseHeatmapButton();
    loadRareOverview("");
    renderDiseaseCards(diseases);
    updateGridSubtitle();
    return;
  }

  selectedIndividualId = pid;
  syncCrossDiseaseHeatmapButton();
  updateGridSubtitle();
  loadRareOverview(pid);
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
    const data = await postJSON(
      "/api/disease-risk-overview",
      {
        individual_id: pid,
        cohort: selectedCohortSlug,
      },
      OVERVIEW_NETWORK_RETRY_DELAYS_MS,
    );
    if (requestId !== diseaseOverviewRequestId || pid !== selectedIndividualId) return;
    renderDiseaseCards(Array.isArray(data.diseases) ? data.diseases : []);
  } catch (err) {
    if (requestId !== diseaseOverviewRequestId) return;
    if (grid) {
      const message = err instanceof TypeError
        ? t("overviewConnectionFailed")
        : err.message;
      grid.innerHTML = `
        <div class="empty-state">
          <span class="material-symbols-outlined" aria-hidden="true">error</span>
          <p>${escapeHtml(message)}</p>
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
  selectedIndividualId = new URLSearchParams(window.location.search).get("individual_id") || "";

  try {
    await exchangeKpredictTokenFromFragment();
    await loadCohorts();
    await loadDiseases();
    await loadIndividuals();
    await loadDiseaseOverview();
  } catch (err) {
    setCohortSelectMessage(t("portalLoadFailed"));
    setText("individual-status", err.message);
  }

  $("language-toggle-top")?.addEventListener("click", toggleLanguage);
  $("theme-toggle-top")?.addEventListener("click", toggleTheme);
  document.addEventListener("click", (event) => {
    if (!event.target?.closest?.(".rare-summary-help")) {
      hideRareSummaryTooltip({ force: true });
    }
  });
  window.addEventListener("resize", positionRareSummaryTooltip);
  window.addEventListener("scroll", positionRareSummaryTooltip, true);

  window.addEventListener("storage", (event) => {
    if (event.key === LANGUAGE_PREFERENCE_KEY && event.newValue) {
      applyLanguage(event.newValue);
    }
    if (event.key === THEME_PREFERENCE_KEY && event.newValue) {
      applyTheme(event.newValue);
    }
  });

  $("individual-search")?.addEventListener("input", scheduleIndividualFilter);
  $("rare-overview-content")?.addEventListener("click", (event) => {
    const trigger = event.target?.closest?.("[data-rare-detail-index]");
    if (trigger) openRareOverviewDetail(trigger.dataset.rareDetailIndex);
  });
  $("kpredict-access-form")?.addEventListener("submit", submitPrivateCohortAccess);
  $("kpredict-access-close-btn")?.addEventListener("click", () => {
    closePrivateCohortAccess({ returnToPublic: true });
  });
  $("kpredict-access-cancel-btn")?.addEventListener("click", () => {
    closePrivateCohortAccess({ returnToPublic: true });
  });

  $("cohort-select")?.addEventListener("change", async () => {
    window.XPRSRareVariantDrawer?.close();
    selectedCohortSlug = $("cohort-select").value || "1000_genomes";
    selectedIndividualId = "";
    clearRiskFilter({ refreshOverview: false, render: false });
    rareOverviewRequestId += 1;
    rareOverviewData = null;
    geneHeatmapData = null;
    populationGeneArchitectureData = null;
    closeGeneHeatmap();
    clearIndividualSearch();
    updateCohortStatus();
    syncCrossDiseaseHeatmapButton();
    syncRiskFilterAvailability();
    syncRareOverviewAvailability();
    await loadIndividuals();
    await loadDiseaseOverview();
  });

  $("individual-id")?.addEventListener("change", () => {
    window.XPRSRareVariantDrawer?.close();
    selectedIndividualId = $("individual-id").value || "";
    geneHeatmapData = null;
    closeGeneHeatmap();
    syncCrossDiseaseHeatmapButton();
    if (selectedCohortSlug === "1000_genomes" && selectedIndividualId) {
      savePreference(INDIVIDUAL_PREFERENCE_KEY, selectedIndividualId);
    }
    loadDiseaseOverview();
  });

  $("refresh-grid-btn")?.addEventListener("click", () => {
    loadDiseaseOverview();
  });

  $("cross-disease-heatmap-btn")?.addEventListener("click", openGeneHeatmap);
  $("gene-heatmap-close-btn")?.addEventListener("click", closeGeneHeatmap);
  $("individual-heatmap-tab")?.addEventListener("click", () => {
    selectGeneComparisonView("individual");
  });
  $("population-architecture-tab")?.addEventListener("click", () => {
    selectGeneComparisonView("population");
  });
  $("population-architecture-controls")?.addEventListener("submit", (event) => {
    event.preventDefault();
    populationGeneArchitectureData = null;
    loadPopulationGeneArchitecture();
  });
  $("gene-heatmap-overlay")?.addEventListener("click", (event) => {
    if (event.target === $("gene-heatmap-overlay")) closeGeneHeatmap();
  });
  $("risk-filter-open-btn")?.addEventListener("click", openRiskFilter);
  $("risk-filter-close-btn")?.addEventListener("click", closeRiskFilter);
  $("risk-filter-cancel-btn")?.addEventListener("click", closeRiskFilter);
  $("risk-filter-clear-btn")?.addEventListener("click", () => clearRiskFilter());
  $("risk-filter-form")?.addEventListener("submit", applyRiskFilter);
  $("risk-filter-band")?.addEventListener("change", () => {
    const band = $("risk-filter-band")?.value || "top_10";
    const order = $("risk-filter-order");
    if (order) order.value = band.startsWith("bottom_") ? "asc" : "desc";
  });
  $("risk-filter-overlay")?.addEventListener("click", (event) => {
    if (event.target === $("risk-filter-overlay")) closeRiskFilter();
  });
  document.addEventListener("keydown", (event) => {
    const rareDetailOverlay = $("rare-detail-overlay");
    if (event.key === "Escape" && rareDetailOverlay && !rareDetailOverlay.hidden) {
      window.XPRSRareVariantDrawer?.close();
      return;
    }
    if (event.key === "Escape" && isGeneHeatmapOpen()) closeGeneHeatmap();
    if (event.key === "Escape" && !$("risk-filter-overlay")?.hidden) closeRiskFilter();
    if (event.key === "Escape" && !$("kpredict-access-overlay")?.hidden) {
      closePrivateCohortAccess({ returnToPublic: true });
    }
  });

  $("disease-grid")?.addEventListener("click", (event) => {
    const card = event.target?.closest?.("[data-disease]");
    if (!card) return;
    openDashboardForDisease(card.dataset.disease);
  });

});
