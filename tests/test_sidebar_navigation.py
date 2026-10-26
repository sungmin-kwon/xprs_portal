import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class GlobalNavigationTests(unittest.TestCase):
    def _read(self, filename: str) -> str:
        return (STATIC / filename).read_text(encoding="utf-8")

    def test_legacy_sidebar_is_removed_from_primary_pages(self):
        for filename in ("home.html", "dashboard.html", "about.html"):
            with self.subTest(filename=filename):
                html = self._read(filename)
                self.assertNotIn('<nav class="sidebar"', html)
                self.assertNotIn('id="sidebar-breast-portal"', html)

    def test_evaluation_navigation_is_deferred_on_primary_pages(self):
        home = self._read("home.html")
        self.assertIn("topbar-link--disabled-icon", home)
        self.assertIn('aria-disabled="true"', home)
        self.assertNotIn('href="/evaluation" title="User evaluation survey"', home)

        dashboard = self._read("dashboard.html")
        self.assertIn("global-nav-link--disabled-icon", dashboard)
        self.assertIn('aria-disabled="true"', dashboard)
        self.assertNotIn('href="/evaluation" title="User evaluation survey"', dashboard)

        about = self._read("about.html")
        self.assertIn('href="/evaluation"', about)
        self.assertIn("data-evaluation-link hidden", about)

        for filename in ("home.js", "dashboard.js"):
            with self.subTest(filename=filename):
                script = self._read(filename)
                self.assertNotIn("syncEvaluationAvailability", script)
                self.assertNotIn("data-evaluation-link", script)

        about_script = self._read("about.js")
        self.assertIn("evaluation_enabled", about_script)
        self.assertIn("data-evaluation-link", about_script)

    def test_overview_topbar_contains_global_actions_and_cohort_selector(self):
        html = self._read("home.html")
        self.assertIn('class="topbar-brand" href="/"', html)
        self.assertIn('id="cohort-select"', html)
        self.assertIn('class="topbar-link" href="/about"', html)
        self.assertIn("topbar-link--disabled-icon", html)

    def test_dashboard_topbar_preserves_context(self):
        html = self._read("dashboard.html")
        script = self._read("dashboard.js")
        self.assertIn('id="overview-back-link"', html)
        self.assertIn('id="dashboard-cohort-label-text"', html)
        self.assertIn('class="global-nav-link" href="/about"', html)
        self.assertIn("function syncDashboardNavigation()", script)
        self.assertIn('params.set("individual_id", individualId)', script)
        self.assertIn('t("privateCohortLabel")', script)
        self.assertIn('t("publicCohortLabel")', script)

    def test_methodology_uses_global_navigation_without_legacy_lookup(self):
        html = self._read("about.html")
        script = self._read("about.js")
        self.assertIn('class="about-topbar"', html)
        self.assertIn('href="/"', html)
        self.assertIn('href="/about" aria-current="page"', html)
        self.assertIn('src="/static/about.js?v=3"', html)
        self.assertNotIn("configureBreastCancerPortalLink", script)
        self.assertNotIn("/api/individuals?cohort=1000_genomes", script)

    def test_selected_individual_is_shared_between_overview_and_dashboard(self):
        for filename in ("home.js", "dashboard.js"):
            with self.subTest(filename=filename):
                script = self._read(filename)
                self.assertIn('INDIVIDUAL_PREFERENCE_KEY = "xprs.individual_id"', script)

        home_script = self._read("home.js")
        dashboard_script = self._read("dashboard.js")
        self.assertIn('get("individual_id") || ""', home_script)
        self.assertIn(
            'readPreference(INDIVIDUAL_PREFERENCE_KEY, "")',
            dashboard_script,
        )


if __name__ == "__main__":
    unittest.main()
