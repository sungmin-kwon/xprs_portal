(function () {
  "use strict";

  const TEXT = {
    en: {
      eyebrow: "RARE-VARIANT DETAILS",
      close: "Close rare-variant details",
      alert: "Alert",
      carrier: "Carrier",
      finding: "Finding",
      alertDescription: "The source data designated this finding for prominent review. It is not a diagnosis.",
      carrierDescription: "The source data classified this as a heterozygous finding for a recessive condition. It generally indicates carrier status rather than disease.",
      findingDescription: "This finding has no alert or carrier classification in the supplied data.",
      variantSection: "Variant",
      clinicalSection: "Clinical annotation",
      panelSection: "Disease-panel interpretation",
      frequencySection: "Frequency context",
      gene: "Gene",
      hgvs: "HGVS",
      genomicVariant: "Genomic variant",
      dbsnp: "dbSNP ID",
      genotype: "Genotype",
      consequence: "Molecular consequence",
      consequenceClass: "Consequence class",
      clinvarSignificance: "ClinVar classification",
      clinvarReview: "ClinVar review level",
      confidenceTier: "Confidence tier",
      conditions: "ClinVar condition(s)",
      category: "Finding category",
      panelappMoi: "PanelApp inheritance",
      panelappPanels: "PanelApp panels",
      clingenMoi: "ClinGen inheritance",
      clingenTier: "ClinGen evidence tier",
      clingenDetail: "ClinGen detail",
      classificationReason: "Why this classification",
      unassigned: "Not assigned to an XPRS disease panel",
      cohortAf: "Cohort allele frequency",
      gnomadAf: "gnomAD allele frequency",
      gnomadEasAf: "gnomAD East Asian frequency",
      easContext: "East Asian frequency context",
      openClinvar: "Open in ClinVar",
      noPanelDetails: "No disease-panel assignment is recorded for this finding.",
      boundary: "These are supplied research annotations. They do not establish a diagnosis, prognosis, or causal relationship with the selected disease.",
      stars: (count) => `${count} of 4 stars`,
    },
    ko: {
      eyebrow: "희귀 변이 상세",
      close: "희귀 변이 상세 닫기",
      alert: "주의",
      carrier: "보인자",
      finding: "소견",
      alertDescription: "원자료에서 우선 검토 대상으로 지정한 소견입니다. 질환 진단을 의미하지 않습니다.",
      carrierDescription: "원자료에서 열성 질환과 관련된 이형접합 소견으로 분류했습니다. 일반적으로 질환 발병이 아니라 보인자 상태를 의미합니다.",
      findingDescription: "원자료에 주의 또는 보인자 분류가 없는 소견입니다.",
      variantSection: "변이 정보",
      clinicalSection: "임상 주석",
      panelSection: "질환 패널 해석",
      frequencySection: "빈도 정보",
      gene: "유전자",
      hgvs: "HGVS",
      genomicVariant: "유전체 변이",
      dbsnp: "dbSNP ID",
      genotype: "유전자형",
      consequence: "분자적 결과",
      consequenceClass: "결과 분류",
      clinvarSignificance: "ClinVar 분류",
      clinvarReview: "ClinVar 검토 수준",
      confidenceTier: "신뢰도 등급",
      conditions: "ClinVar 질환",
      category: "소견 분류",
      panelappMoi: "PanelApp 유전 양식",
      panelappPanels: "PanelApp 패널 수",
      clingenMoi: "ClinGen 유전 양식",
      clingenTier: "ClinGen 근거 등급",
      clingenDetail: "ClinGen 상세",
      classificationReason: "이 분류의 근거",
      unassigned: "XPRS 질환 패널에 배정되지 않음",
      cohortAf: "코호트 대립유전자 빈도",
      gnomadAf: "gnomAD 대립유전자 빈도",
      gnomadEasAf: "gnomAD 동아시아 빈도",
      easContext: "동아시아 빈도 정보",
      openClinvar: "ClinVar에서 열기",
      noPanelDetails: "이 소견에는 질환 패널 배정이 없습니다.",
      boundary: "이 정보는 제공받은 연구용 주석입니다. 진단, 예후 또는 선택한 질환과의 인과관계를 확정하지 않습니다.",
      stars: (count) => `4점 중 ${count}점`,
    },
  };

  let currentItem = null;
  let currentOptions = {};
  let previousFocus = null;

  function language() {
    return currentOptions.language === "ko" ? "ko" : "en";
  }

  function tr(key, ...args) {
    const value = TEXT[language()][key] ?? TEXT.en[key] ?? key;
    return typeof value === "function" ? value(...args) : value;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function present(value) {
    if (value === null || value === undefined) return false;
    const normalized = String(value).trim().toLowerCase();
    return !["", "nan", "none", "null", "na", "n/a"].includes(normalized);
  }

  function pretty(value) {
    return present(value) ? String(value).replaceAll("_", " ") : "";
  }

  function formatFrequency(value) {
    if (!present(value)) return "";
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return pretty(value);
    const proportion = numeric === 0
      ? "0"
      : (Math.abs(numeric) < 0.0001 ? numeric.toExponential(2) : numeric.toLocaleString(undefined, { maximumSignificantDigits: 5 }));
    const percent = (numeric * 100).toLocaleString(undefined, { maximumSignificantDigits: 4 });
    return `${proportion} (${percent}%)`;
  }

  function detailField(label, value, className = "") {
    if (!present(value)) return "";
    return `<div class="rare-detail-field${className ? ` ${className}` : ""}">
      <dt>${escapeHtml(label)}</dt>
      <dd>${escapeHtml(pretty(value))}</dd>
    </div>`;
  }

  function section(title, contents) {
    const visible = contents.filter(Boolean).join("");
    if (!visible) return "";
    return `<section class="rare-detail-section">
      <h3>${escapeHtml(title)}</h3>
      <dl class="rare-detail-grid">${visible}</dl>
    </section>`;
  }

  function callValue(item) {
    return String(item?.call || item?.moi_call || "").toLowerCase();
  }

  function callLabel(call) {
    return tr(call === "alert" ? "alert" : call === "carrier" ? "carrier" : "finding");
  }

  function callDescription(call) {
    return tr(call === "alert" ? "alertDescription" : call === "carrier" ? "carrierDescription" : "findingDescription");
  }

  function diseaseLabel(assignment) {
    if (typeof currentOptions.diseaseLabel === "function") {
      return currentOptions.diseaseLabel(
        assignment.disease || assignment.xprs_disease || "",
        assignment.disease_label || assignment.xprs_disease_label || "",
      );
    }
    return assignment.disease_label || assignment.xprs_disease_label || assignment.disease || assignment.xprs_disease || "";
  }

  function normalizedAssignments(item) {
    if (Array.isArray(item.panel_assignments) && item.panel_assignments.length) {
      return item.panel_assignments;
    }
    if (present(item.xprs_disease) || present(item.xprs_disease_label)) {
      return [{
        ...item,
        disease: item.xprs_disease,
        disease_label: item.xprs_disease_label,
      }];
    }
    return [];
  }

  function panelAssignment(assignment) {
    const call = callValue(assignment);
    const fields = [
      detailField(tr("classificationReason"), assignment.moi_why, "is-wide"),
      detailField(tr("panelappMoi"), assignment.panelapp_moi),
      detailField(tr("panelappPanels"), assignment.panelapp_n_panels),
      detailField(tr("clingenMoi"), assignment.clingen_moi),
      detailField(tr("clingenTier"), assignment.clingen_tier),
      detailField(tr("clingenDetail"), assignment.clingen_detail, "is-wide"),
    ].filter(Boolean).join("");
    return `<article class="rare-detail-assignment">
      <header>
        <strong>${escapeHtml(diseaseLabel(assignment) || tr("unassigned"))}</strong>
        <span class="rare-detail-call is-${escapeHtml(call || "finding")}">${escapeHtml(callLabel(call))}</span>
      </header>
      ${fields ? `<dl class="rare-detail-grid">${fields}</dl>` : ""}
    </article>`;
  }

  function clinvarLink(item) {
    const query = String(item.hgvs || item.rsid || item.variant || "").trim();
    if (!query) return "";
    const url = `https://www.ncbi.nlm.nih.gov/clinvar/?term=${encodeURIComponent(query)}`;
    return `<a class="rare-detail-clinvar" href="${url}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">
      <span>${escapeHtml(tr("openClinvar"))}</span>
      <span class="material-symbols-outlined" aria-hidden="true">open_in_new</span>
    </a>`;
  }

  function render() {
    if (!currentItem) return;
    ensureDrawer();
    const item = currentItem;
    const call = callValue(item);
    const gene = present(item.gene) ? item.gene : "—";
    const primaryVariant = item.hgvs || item.variant || item.rsid || "";
    const stars = Number(item.stars);
    const review = Number.isFinite(stars) ? `${"★".repeat(Math.max(0, Math.min(4, stars)))}${"☆".repeat(Math.max(0, 4 - Math.min(4, stars)))} · ${tr("stars", stars)}` : "";
    const assignments = normalizedAssignments(item);

    document.getElementById("rare-detail-eyebrow").textContent = tr("eyebrow");
    document.getElementById("rare-detail-title").textContent = gene;
    document.getElementById("rare-detail-subtitle").textContent = primaryVariant;
    const closeButton = document.getElementById("rare-detail-close");
    closeButton.setAttribute("aria-label", tr("close"));
    closeButton.setAttribute("title", tr("close"));

    const variantSection = section(tr("variantSection"), [
      detailField(tr("gene"), item.gene),
      detailField(tr("hgvs"), item.hgvs, "is-monospace"),
      detailField(tr("genomicVariant"), item.variant, "is-monospace"),
      detailField(tr("dbsnp"), item.rsid, "is-monospace"),
      detailField(tr("genotype"), item.genotype),
      detailField(tr("consequence"), item.consequence),
      detailField(tr("consequenceClass"), item.consequence_class),
    ]);
    const clinicalSection = section(tr("clinicalSection"), [
      detailField(tr("clinvarSignificance"), item.clnsig),
      detailField(tr("clinvarReview"), review),
      detailField(tr("confidenceTier"), item.tier),
      detailField(tr("category"), item.category),
      detailField(tr("conditions"), item.clinvar_conditions, "is-wide"),
    ]);
    const frequencySection = section(tr("frequencySection"), [
      detailField(tr("cohortAf"), formatFrequency(item.cohort_af)),
      detailField(tr("gnomadAf"), formatFrequency(item.gnomad_af)),
      detailField(tr("gnomadEasAf"), formatFrequency(item.gnomad_af_eas)),
      detailField(tr("easContext"), item.eas_specific),
    ]);
    const panelSection = `<section class="rare-detail-section">
      <h3>${escapeHtml(tr("panelSection"))}</h3>
      <div class="rare-detail-assignments">
        ${assignments.length ? assignments.map(panelAssignment).join("") : `<p class="rare-detail-empty">${escapeHtml(tr("noPanelDetails"))}</p>`}
      </div>
    </section>`;

    document.getElementById("rare-detail-body").innerHTML = `
      <div class="rare-detail-status is-${escapeHtml(call || "finding")}">
        <span class="rare-detail-call is-${escapeHtml(call || "finding")}">${escapeHtml(callLabel(call))}</span>
        <p>${escapeHtml(callDescription(call))}</p>
      </div>
      ${variantSection}
      ${clinicalSection}
      ${panelSection}
      ${frequencySection}
      ${clinvarLink(item)}
      <p class="rare-detail-boundary">${escapeHtml(tr("boundary"))}</p>
    `;
  }

  function ensureDrawer() {
    if (document.getElementById("rare-detail-overlay")) return;
    const overlay = document.createElement("div");
    overlay.id = "rare-detail-overlay";
    overlay.className = "rare-detail-overlay";
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");
    overlay.innerHTML = `
      <div class="rare-detail-backdrop" data-rare-detail-close></div>
      <aside class="rare-detail-drawer" role="dialog" aria-modal="true" aria-labelledby="rare-detail-title" aria-describedby="rare-detail-subtitle">
        <header class="rare-detail-header">
          <div>
            <p id="rare-detail-eyebrow"></p>
            <h2 id="rare-detail-title"></h2>
            <p id="rare-detail-subtitle"></p>
          </div>
          <button id="rare-detail-close" class="rare-detail-close" type="button" data-rare-detail-close>
            <span class="material-symbols-outlined" aria-hidden="true">close</span>
          </button>
        </header>
        <div id="rare-detail-body" class="rare-detail-body"></div>
      </aside>`;
    document.body.appendChild(overlay);
    overlay.addEventListener("click", (event) => {
      if (event.target.closest("[data-rare-detail-close]")) close();
    });
    document.addEventListener("keydown", handleKeydown);
  }

  function focusableElements() {
    const drawer = document.querySelector("#rare-detail-overlay .rare-detail-drawer");
    if (!drawer) return [];
    return [...drawer.querySelectorAll('button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])')];
  }

  function handleKeydown(event) {
    const overlay = document.getElementById("rare-detail-overlay");
    if (!overlay || overlay.hidden) return;
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = focusableElements();
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function open(item, options = {}) {
    if (!item) return;
    currentItem = item;
    currentOptions = options;
    previousFocus = document.activeElement;
    render();
    const overlay = document.getElementById("rare-detail-overlay");
    overlay.hidden = false;
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("rare-detail-open");
    window.requestAnimationFrame(() => overlay.classList.add("is-open"));
    document.getElementById("rare-detail-close")?.focus();
  }

  function close() {
    const overlay = document.getElementById("rare-detail-overlay");
    if (!overlay || overlay.hidden) return;
    overlay.classList.remove("is-open");
    overlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("rare-detail-open");
    window.setTimeout(() => {
      overlay.hidden = true;
      if (previousFocus && document.contains(previousFocus)) previousFocus.focus();
    }, 180);
  }

  function refresh(options = {}) {
    currentOptions = { ...currentOptions, ...options };
    const overlay = document.getElementById("rare-detail-overlay");
    if (currentItem && overlay && !overlay.hidden) render();
  }

  window.XPRSRareVariantDrawer = { open, close, refresh };
}());
