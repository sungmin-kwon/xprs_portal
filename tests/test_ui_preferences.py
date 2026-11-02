import re
import unittest

from tests.support import ContractTestCase, ROOT, STATIC


class UiContractTests(ContractTestCase):
    def test_admin_and_cohort_analysis_contracts(self):
        self.run_contract_checks((
            "_check_admin_retrieval_page_exposes_the_background_request_backlog",
            "_check_cohort_analysis_is_a_distinct_protected_population_view",
        ))

    def test_preferences_copy_and_search_contracts(self):
        self.run_contract_checks((
            "_check_dashboard_page_is_not_reused_across_frontend_deployments",
            "_check_landing_page_has_theme_toggle_and_dark_palette",
            "_check_landing_and_dashboard_use_the_same_preference_keys",
            "_check_dashboard_no_longer_forces_light_and_english_defaults",
            "_check_unavailable_cohort_message_is_consistent_and_plain",
            "_check_overview_and_dashboard_use_natural_individual_counts_and_korean_copy",
            "_check_individual_search_is_bounded_debounced_and_batched",
        ))

    def test_dashboard_evidence_contracts(self):
        self.run_contract_checks((
            "_check_third_visualization_is_reserved_for_rare_variants",
            "_check_visualization_rows_are_equal_and_rare_list_scrolls_internally",
            "_check_rare_variant_ui_uses_three_distinct_source_groups",
            "_check_dashboard_has_integrated_common_and_rare_evidence_view",
        ))

    def test_overview_analysis_contracts(self):
        self.run_contract_checks((
            "_check_overview_has_private_cross_disease_gene_heatmap_modal",
            "_check_overview_places_cohort_selector_in_topbar",
            "_check_overview_consolidates_panel_findings_into_disease_cards",
            "_check_overview_can_filter_private_individuals_by_disease_risk",
            "_check_public_overview_uses_single_disease_presentation",
            "_check_overview_density_plots_use_percentile_based_diverging_tints",
        ))

    def test_rare_variant_contracts(self):
        self.run_contract_checks((
            "_check_overview_has_grouped_rare_variant_side_pane",
            "_check_private_cohort_access_uses_an_inline_validation_dialog",
            "_check_rare_variant_hgvs_values_link_to_clinvar_without_referrers",
            "_check_private_rare_findings_open_an_accessible_detail_drawer",
        ))

    def _check_admin_retrieval_page_exposes_the_background_request_backlog(self):
        html = (STATIC / "admin-documents.html").read_text(encoding="utf-8")
        script = (STATIC / "admin-documents.js").read_text(encoding="utf-8")
        routes = (ROOT / "routes" / "admin_documents.py").read_text(encoding="utf-8")

        self.assertIn('id="queue-backlog"', html)
        self.assertIn('id="queue-backlog-list"', html)
        self.assertIn('class="fallback-menu"', html)
        self.assertNotIn('class="health-grid"', html)
        self.assertIn('id="admin-access-dialog"', html)
        self.assertIn('id="admin-access-form"', html)
        self.assertIn('type="password"', html)
        self.assertIn("pendingJobForPool", script)
        self.assertIn("requestAccessCode", script)
        self.assertIn("The admin access code was not accepted.", script)
        self.assertIn('hasIndexableCache ? "Index cache"', script)
        self.assertIn('canContinue ? "Continue search"', script)
        self.assertNotIn('"Resume indexing"', script)
        self.assertNotIn("window.prompt", script)
        self.assertIn('pendingJob.state === "queued" ? "Queued" : "In progress"', script)
        self.assertIn("Tracked query pools", html)
        self.assertNotIn("Frequent-gene plan", html)
        self.assertNotIn("Outside the plan", html)
        self.assertNotIn("Top/bottom appearances", html)
        self.assertIn('"europe_pmc": EUROPE_PMC_CACHE_DIR', routes)

    def _check_cohort_analysis_is_a_distinct_protected_population_view(self):
        html = (STATIC / "cohort_analysis.html").read_text(encoding="utf-8")
        script = (STATIC / "cohort_analysis.js").read_text(encoding="utf-8")
        css = (STATIC / "cohort_analysis.css").read_text(encoding="utf-8")
        routes = (ROOT / "routes" / "kpredict.py").read_text(encoding="utf-8")
        pages = (ROOT / "routes" / "pages.py").read_text(encoding="utf-8")

        self.assertIn('id="distribution-plot"', html)
        self.assertIn('id="gene-table-body"', html)
        self.assertIn('id="individual-table-body"', html)
        self.assertIn("PRS and Rare-Variant Cohort Analysis", html)
        self.assertIn('class="intro-question"', html)
        self.assertIn('class="filter-mode filter-mode--immediate"', html)
        self.assertIn('id="staged-filter-group"', html)
        self.assertNotIn("Updates immediately", html)
        self.assertNotIn("Apply together", html)
        self.assertNotIn('data-i18n="filtersHelp"', html)
        self.assertIn("/api/kpredict/cohort-analysis", script)
        self.assertIn("cumulative_percent", script)
        self.assertIn("individual_limit: 200", script)
        self.assertIn("function syncPendingFilterState()", script)
        self.assertIn("loadAnalysis(appliedFilters)", script)
        self.assertNotIn("raw_prs", script)
        self.assertNotIn(">People<", html)
        self.assertIn("Genes with panel findings", html)
        self.assertIn("How were disease-panel findings defined?", html)
        self.assertIn("cardiacPanelCaveat", script)
        self.assertIn(":root[data-theme=\"dark\"]", css)
        self.assertIn(".filter-mode--immediate", css)
        self.assertIn(".filter-mode--staged.has-pending-changes", css)
        self.assertIn('router.get("/api/kpredict/cohort-analysis"', routes)
        self.assertIn("root = require_kpredict_access(request)", routes)
        self.assertIn('@router.get("/cohort-analysis")', pages)

    def _check_dashboard_page_is_not_reused_across_frontend_deployments(self):
        pages = (ROOT / "routes" / "pages.py").read_text(encoding="utf-8")

        self.assertIn('"Cache-Control": "no-store, max-age=0"', pages)
        self.assertIn("FileResponse(STATIC_DIR / \"dashboard.html\", headers=PAGE_HEADERS)", pages)

    def _check_landing_page_has_theme_toggle_and_dark_palette(self):
        html = (STATIC / "home.html").read_text(encoding="utf-8")
        css = (STATIC / "home.css").read_text(encoding="utf-8")
        self.assertIn('id="theme-toggle-top"', html)
        self.assertIn("body.dark-theme", css)

    def _check_landing_and_dashboard_use_the_same_preference_keys(self):
        for filename in ("home.js", "dashboard.js"):
            with self.subTest(filename=filename):
                script = (STATIC / filename).read_text(encoding="utf-8")
                self.assertIn('LANGUAGE_PREFERENCE_KEY = "xprs.language"', script)
                self.assertIn('THEME_PREFERENCE_KEY = "xprs.theme"', script)
                self.assertIn("window.localStorage.getItem", script)
                self.assertIn("window.localStorage.setItem", script)

    def _check_dashboard_no_longer_forces_light_and_english_defaults(self):
        script = (STATIC / "dashboard.js").read_text(encoding="utf-8")
        dom_ready = script[script.index('window.addEventListener("DOMContentLoaded"') :]
        self.assertNotIn('applyTheme("light")', dom_ready)
        self.assertRegex(
            dom_ready,
            re.compile(r'readPreference\(LANGUAGE_PREFERENCE_KEY,\s*"en"\)'),
        )
        self.assertRegex(
            dom_ready,
            re.compile(r'readPreference\(THEME_PREFERENCE_KEY,\s*"light"\)'),
        )
        self.assertIn("syncLanguageInUrl();", script)

    def _check_third_visualization_is_reserved_for_rare_variants(self):
        html = (STATIC / "dashboard.html").read_text(encoding="utf-8")
        script = (STATIC / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn('data-i18n="rareVariantTitle"', html)
        self.assertIn('data-i18n="rareVariantUnavailable"', html)
        self.assertIn('rareVariantTitle: "희귀 변이 분석"', script)
        self.assertNotIn("Visualization Placeholder", html)
        self.assertNotIn("Reserved for future analysis panel", html)

    def _check_visualization_rows_are_equal_and_rare_list_scrolls_internally(self):
        css = (STATIC / "dashboard.css").read_text(encoding="utf-8")

        self.assertIn("grid-template-rows: repeat(3, minmax(0, 1fr));", css)
        self.assertRegex(
            css,
            re.compile(r"#rare-variant-content\s*\{[^}]*overflow-y:\s*auto", re.DOTALL),
        )

    def _check_rare_variant_ui_uses_three_distinct_source_groups(self):
        script = (STATIC / "dashboard.js").read_text(encoding="utf-8")

        self.assertIn("data.active_disease_group", script)
        self.assertIn("data.other_disease_groups", script)
        self.assertIn("data.unassigned_group", script)
        self.assertIn("rareOtherDiseasePanels", script)
        self.assertIn("rareUnassignedFindings", script)

    def _check_unavailable_cohort_message_is_consistent_and_plain(self):
        script = (STATIC / "home.js").read_text(encoding="utf-8")

        self.assertIn('cohortDataUnavailable: "No data available for this cohort."', script)
        self.assertIn('cohortDataUnavailable: "이 코호트에 해당하는 데이터가 없습니다."', script)
        self.assertIn('if (cohort && !cohort.data_available) return t("cohortDataUnavailable");', script)
        self.assertNotIn("No XPRS model data are configured yet", script)
        self.assertNotIn("XPRS model data are not configured for this disease yet", script)

    def _check_overview_and_dashboard_use_natural_individual_counts_and_korean_copy(self):
        home = (STATIC / "home.js").read_text(encoding="utf-8")
        dashboard = (STATIC / "dashboard.js").read_text(encoding="utf-8")

        for script in (home, dashboard):
            self.assertIn("individuals found", script)
            self.assertIn("`총 ${count}명", script)

        self.assertIn('modelDataUnavailable: "이 질환에 해당하는 데이터가 없습니다."', home)
        self.assertIn('findIndividualsByRisk: "질환별 위험도 검색"', home)
        self.assertIn('riskFilterTitle: "질환별 위험도 검색"', home)
        self.assertNotIn("사용 가능한 개인 ID", home)
        self.assertNotIn("위험도로 개인 찾기", home)
        self.assertNotIn("질환별 작업공간", home)
        self.assertIn('individualId: "개인 ID"', dashboard)
        self.assertNotIn("개인 ID ${count}개 불러오기 완료", dashboard)

    def _check_individual_search_is_bounded_debounced_and_batched(self):
        for filename in ("home.js", "dashboard.js"):
            with self.subTest(filename=filename):
                script = (STATIC / filename).read_text(encoding="utf-8")
                self.assertIn("INDIVIDUAL_SEARCH_LIMIT = 200", script)
                self.assertIn("INDIVIDUAL_SEARCH_DEBOUNCE_MS = 120", script)
                self.assertIn("document.createDocumentFragment()", script)
                self.assertIn("replaceChildren(fragment)", script)
                self.assertIn("scheduleIndividualFilter", script)
                self.assertNotIn(
                    'addEventListener("input", filterIndividuals)',
                    script,
                )

        dashboard = (STATIC / "dashboard.js").read_text(encoding="utf-8")
        filter_block = dashboard[
            dashboard.index("function filterIndividuals()") :
            dashboard.index("// Plot loading")
        ]
        self.assertNotIn("updateGeneSelectionPreview", filter_block)
        self.assertNotIn('individualSelect.addEventListener("input"', dashboard)
        self.assertNotIn('individualSelect.addEventListener("click"', dashboard)

    def _check_overview_has_private_cross_disease_gene_heatmap_modal(self):
        html = (STATIC / "home.html").read_text(encoding="utf-8")
        script = (STATIC / "home.js").read_text(encoding="utf-8")
        css = (STATIC / "home.css").read_text(encoding="utf-8")

        self.assertIn('id="cross-disease-heatmap-btn"', html)
        self.assertIn('id="gene-heatmap-overlay"', html)
        self.assertIn('id="gene-heatmap-plot"', html)
        self.assertIn('id="population-architecture-tab"', html)
        self.assertIn('id="population-architecture-plot"', html)
        self.assertIn("/api/kpredict/cross-disease-gene-heatmap", script)
        self.assertIn("/api/kpredict/population-gene-architecture", script)
        self.assertIn('type: "heatmap"', script)
        self.assertIn('selectedCohortSlug !== "kpredict"', script)
        self.assertIn('geneHeatmapTitle: "Gene Contributions Across Diseases"', script)
        self.assertIn('geneHeatmapTitle: "질환별 유전자 기여도 비교"', script)
        self.assertIn('exploratoryAnalysis: "Cross-Disease Comparison"', script)
        self.assertIn("집단 분산의 제곱근으로 나눈 값", script)
        self.assertIn("const missingValues = values.map", script)
        self.assertIn("const hoverLabels = values.map", script)
        self.assertIn("No standardized contribution available", script)
        self.assertIn("they are not zeros", script)
        self.assertIn('hovertemplate: "<b>%{y}</b><br>%{x}<br>%{text}<extra></extra>"', script)
        self.assertNotIn('${t("geneHeatmapScale")}: %{z:.2f}', script)
        self.assertIn("window.Plotly.react(plot, traces", script)
        self.assertIn('populationArchitecture: "Population Architecture"', script)
        self.assertIn('populationArchitecture: "집단 유전자 구조"', script)
        self.assertIn("in the same disease model", script)
        self.assertIn("제공된 PRS 모델의 구조", script)
        self.assertIn(".architecture-controls", css)
        self.assertNotIn("Building the cross-disease gene matrix", script)
        self.assertIn(".analysis-modal-overlay", css)

    def _check_overview_places_cohort_selector_in_topbar(self):
        html = (STATIC / "home.html").read_text(encoding="utf-8")
        script = (STATIC / "home.js").read_text(encoding="utf-8")
        css = (STATIC / "home.css").read_text(encoding="utf-8")

        topbar = html[html.index('<header class="topbar">') : html.index("</header>")]
        control_panel = html[
            html.index('<section class="control-panel"') :
            html.index('<section class="disease-panel"')
        ]
        self.assertIn('id="cohort-select"', topbar)
        self.assertNotIn('id="cohort-select"', control_panel)
        self.assertIn('data-i18n="individualSelection"', control_panel)
        self.assertNotIn("Cohort &amp; Individual", control_panel)
        self.assertIn("setCohortSelectMessage", script)
        self.assertRegex(
            css,
            re.compile(r"\.topbar-cohort-select \.select-caret\s*\{[^}]*position:\s*absolute", re.DOTALL),
        )
        self.assertRegex(
            css,
            re.compile(r"\.topbar-cohort-select #cohort-select\s*\{[^}]*padding:\s*0 2\.4rem 0 0\.35rem", re.DOTALL),
        )

    def _check_overview_consolidates_panel_findings_into_disease_cards(self):
        html = (STATIC / "home.html").read_text(encoding="utf-8")
        script = (STATIC / "home.js").read_text(encoding="utf-8")
        css = (STATIC / "home.css").read_text(encoding="utf-8")

        self.assertNotIn('id="cross-disease-profile-btn"', html)
        self.assertNotIn('id="disease-profile-overlay"', html)
        self.assertNotIn("/api/kpredict/cross-disease-profile", script)
        self.assertIn("card.panel_findings", script)
        self.assertIn('" is-prs-separate" : " is-alert"', script)
        self.assertIn('t("rareEvidenceWithoutPrsHelp")', script)
        self.assertIn('t("prsNotApplicable")', script)
        self.assertIn('t("prsUnavailableStatus")', script)
        self.assertIn("const rareEvidence = rareBadges.length", script)
        self.assertNotIn("const rareEvidence = isAvailable &&", script)
        self.assertIn(".card-rare-evidence", css)
        self.assertIn(".card-rare-badge.is-prs-separate", css)
        self.assertIn("grid-auto-rows: minmax(300px, 1fr)", css)
        self.assertRegex(
            css,
            re.compile(r"\.disease-card\s*\{[^}]*min-height:\s*300px", re.DOTALL),
        )
        self.assertNotIn(".profile-summary", css)

    def _check_overview_can_filter_private_individuals_by_disease_risk(self):
        html = (STATIC / "home.html").read_text(encoding="utf-8")
        script = (STATIC / "home.js").read_text(encoding="utf-8")
        css = (STATIC / "home.css").read_text(encoding="utf-8")

        self.assertIn('id="risk-filter-open-btn"', html)
        self.assertIn('id="risk-filter-disease"', html)
        self.assertIn('id="risk-filter-band"', html)
        self.assertIn('id="risk-filter-order"', html)
        self.assertIn("/api/kpredict/individual-risk-filter", script)
        self.assertIn("top_10: { minimum: 90, maximum: 100 }", script)
        self.assertIn("riskPercentileById.get(pid)", script)
        self.assertIn(".risk-filter-fields", css)

    def _check_overview_has_grouped_rare_variant_side_pane(self):
        html = (STATIC / "home.html").read_text(encoding="utf-8")
        script = (STATIC / "home.js").read_text(encoding="utf-8")
        css = (STATIC / "home.css").read_text(encoding="utf-8")

        self.assertIn('id="rare-overview-panel"', html)
        self.assertIn('id="rare-overview-content"', html)
        self.assertIn("/api/kpredict/rare-findings-overview", script)
        self.assertIn("rareOverviewDiseaseName", script)
        self.assertIn(".overview-layout.has-rare-pane", css)
        self.assertIn(".rare-disease-badge", css)
        self.assertIn("rareOverviewAlertGenes", script)
        self.assertIn("rareOverviewCarrierGenes", script)
        self.assertIn('item.call === "alert" && item.gene', script)
        self.assertIn('item.call === "carrier" && item.gene', script)
        self.assertIn("rareAlertHelp", script)
        self.assertIn("rareCarrierHelp", script)
        self.assertNotIn("rareOverviewNote", script)
        self.assertNotIn("rare-overview-footnote", html)
        self.assertNotIn(".rare-overview-footnote", css)
        self.assertIn('id="rare-summary-tooltip"', html)
        self.assertIn('aria-expanded="false"', script)
        self.assertIn("positionRareSummaryTooltip", script)
        self.assertIn("button.getBoundingClientRect()", script)
        self.assertIn('showRareSummaryTooltip(button, { pinned: true })', script)
        self.assertIn(".rare-summary-tooltip {", css)
        self.assertIn("position: fixed;", css)
        self.assertIn(".rare-summary-tooltip.is-above::before", css)

    def _check_private_cohort_access_uses_an_inline_validation_dialog(self):
        html = (STATIC / "home.html").read_text(encoding="utf-8")
        script = (STATIC / "home.js").read_text(encoding="utf-8")
        css = (STATIC / "home.css").read_text(encoding="utf-8")

        self.assertIn('id="kpredict-access-overlay"', html)
        self.assertIn('id="kpredict-access-form"', html)
        self.assertIn('id="kpredict-access-status"', html)
        self.assertIn('type="password"', html)
        self.assertIn("submitPrivateCohortAccess", script)
        self.assertIn("setPrivateAccessStatus(t(\"privateAccessFailed\"), true)", script)
        self.assertNotIn("window.prompt", script)
        self.assertIn(".analysis-modal--access", css)
        self.assertIn(".kpredict-access-status.is-error", css)

    def _check_dashboard_has_integrated_common_and_rare_evidence_view(self):
        html = (STATIC / "dashboard.html").read_text(encoding="utf-8")
        script = (STATIC / "dashboard.js").read_text(encoding="utf-8")
        css = (STATIC / "dashboard.css").read_text(encoding="utf-8")

        self.assertIn('id="evidence-summary-btn"', html)
        self.assertIn('id="evidence-overlay"', html)
        self.assertIn('id="evidence-overlay-body"', html)
        self.assertIn("/api/kpredict/disease-evidence", script)
        self.assertIn("common.increasing_genes", script)
        self.assertIn("common.lowering_genes", script)
        self.assertIn("rare.findings", script)
        self.assertIn('evidenceBoundary: "Common- and rare-variant results are separate evidence layers.', script)
        self.assertIn("하나의 위험 점수로 합산하지 않으며", script)
        self.assertIn(".evidence-layer-grid", css)
        self.assertIn(".evidence-layer--common", css)
        self.assertIn(".evidence-layer--rare", css)

    def _check_rare_variant_hgvs_values_link_to_clinvar_without_referrers(self):
        for filename in ("home.js", "dashboard.js"):
            with self.subTest(filename=filename):
                script = (STATIC / filename).read_text(encoding="utf-8")
                self.assertIn("https://www.ncbi.nlm.nih.gov/clinvar/?term=", script)
                self.assertIn("encodeURIComponent(hgvs)", script)
                self.assertIn('target="_blank"', script)
                self.assertIn('rel="noopener noreferrer"', script)
                self.assertIn('referrerpolicy="no-referrer"', script)
                self.assertIn("clinvarVariantLink(item.hgvs", script)

        for filename in ("home.css", "dashboard.css"):
            with self.subTest(filename=filename):
                css = (STATIC / filename).read_text(encoding="utf-8")
                self.assertIn(".clinvar-variant-link", css)

    def _check_private_rare_findings_open_an_accessible_detail_drawer(self):
        home_html = (STATIC / "home.html").read_text(encoding="utf-8")
        dashboard_html = (STATIC / "dashboard.html").read_text(encoding="utf-8")
        home_script = (STATIC / "home.js").read_text(encoding="utf-8")
        dashboard_script = (STATIC / "dashboard.js").read_text(encoding="utf-8")
        drawer_script = (STATIC / "rare_variant_detail.js").read_text(encoding="utf-8")
        drawer_css = (STATIC / "rare_variant_detail.css").read_text(encoding="utf-8")

        for html in (home_html, dashboard_html):
            self.assertIn("/static/rare_variant_detail.css", html)
            self.assertIn("/static/rare_variant_detail.js", html)
        self.assertIn("data-rare-detail-index", home_script)
        self.assertIn("data-rare-detail-key", dashboard_script)
        self.assertIn("XPRSRareVariantDrawer", home_script)
        self.assertIn("XPRSRareVariantDrawer", dashboard_script)
        self.assertIn('role="dialog"', drawer_script)
        self.assertIn('aria-modal="true"', drawer_script)
        self.assertIn("panel_assignments", drawer_script)
        self.assertIn("moi_why", drawer_script)
        self.assertIn("panelapp_moi", drawer_script)
        self.assertIn("clingen_moi", drawer_script)
        self.assertIn("cohort_af", drawer_script)
        self.assertIn("gnomad_af", drawer_script)
        self.assertIn("rare-detail-boundary", drawer_script)
        self.assertIn(".rare-detail-drawer", drawer_css)
        self.assertIn("body.dark-theme .rare-detail-drawer", drawer_css)

    def _check_public_overview_uses_single_disease_presentation(self):
        script = (STATIC / "home.js").read_text(encoding="utf-8")
        css = (STATIC / "home.css").read_text(encoding="utf-8")

        self.assertIn('singleDiseaseRiskOverview: "Breast Cancer Risk Overview"', script)
        self.assertIn('singleDiseaseRiskOverview: "유방암 위험 개요"', script)
        self.assertIn('visibleDiseaseCards.length === 1', script)
        self.assertIn(".disease-grid.is-single-disease", css)
        self.assertIn("grid-auto-rows: minmax(0, 1fr)", css)
        self.assertIn(".disease-grid.is-single-disease .mini-plot", css)
        self.assertIn(".mini-plot {\n  flex: 1;\n  width: 100%;", css)

    def _check_overview_density_plots_use_percentile_based_diverging_tints(self):
        html = (STATIC / "home.html").read_text(encoding="utf-8")
        script = (STATIC / "home.js").read_text(encoding="utf-8")
        dashboard_script = (STATIC / "dashboard.js").read_text(encoding="utf-8")
        css = (STATIC / "home.css").read_text(encoding="utf-8")

        self.assertIn('class="risk-tint-key"', html)
        self.assertIn('data-i18n="lowerPrsPercentile"', html)
        self.assertIn('data-i18n="higherPrsPercentile"', html)
        self.assertIn("function percentileTint(percentile, darkTheme = false)", script)
        self.assertIn("const midpointStrength = 1 - (Math.abs(value - 0.5) * 2);", script)
        self.assertIn("midpointStrength * 0.06", script)
        self.assertIn("midpointStrength * 0.03", script)
        self.assertIn("fillAlpha.toFixed(3)", script)
        self.assertIn("backgroundAlpha.toFixed(3)", script)
        self.assertIn("const tint = percentileTint(percentile, darkTheme);", script)
        self.assertIn("fillcolor: tint.fill", script)
        self.assertIn("plot_bgcolor: tint.background", script)
        self.assertIn('line: { color: darkTheme ? "#c8d0d8" : "#343a40", width: 2.2 }', script)
        self.assertIn('line: { color: isDarkTheme() ? "#c8d0d8" : "#343a40", width: 2.5 }', dashboard_script)
        self.assertIn('line: { color: "#d23f31", width: 2 }', script)
        self.assertNotIn("tint.solid", script)
        self.assertIn(".risk-tint-key__bar", css)
        self.assertIn("linear-gradient(90deg, #2a7bb5", css)


if __name__ == "__main__":
    unittest.main()
