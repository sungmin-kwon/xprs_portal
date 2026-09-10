import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class SidebarNavigationTests(unittest.TestCase):
    def _sidebar(self, filename: str) -> str:
        html = (STATIC / filename).read_text(encoding="utf-8")
        match = re.search(r'<nav class="sidebar".*?</nav>', html, re.DOTALL)
        self.assertIsNotNone(match, f"No sidebar found in {filename}")
        return match.group(0)

    def test_evaluation_link_is_hidden_until_the_backend_enables_it(self):
        for filename in ("home.html", "dashboard.html", "about.html"):
            with self.subTest(filename=filename):
                sidebar = self._sidebar(filename)
                self.assertRegex(
                    sidebar,
                    r'href="/evaluation"[^>]*data-evaluation-link[^>]*hidden',
                )

        for filename in ("home.js", "dashboard.js", "about.js"):
            with self.subTest(filename=filename):
                script = (STATIC / filename).read_text(encoding="utf-8")
                self.assertIn("evaluation_enabled", script)
                self.assertIn("data-evaluation-link", script)

    def test_brand_icon_links_to_about_instead_of_duplicating_home(self):
        for filename in ("home.html", "dashboard.html", "about.html"):
            with self.subTest(filename=filename):
                sidebar = self._sidebar(filename)
                self.assertRegex(
                    sidebar,
                    r'class="nav-brand" href="/about"',
                )

    def test_dashboard_sidebar_links_are_not_underlined(self):
        css = (STATIC / "dashboard.css").read_text(encoding="utf-8")
        self.assertRegex(
            css,
            r"\.nav-brand,\s*\.nav-item\s*\{\s*text-decoration:\s*none;",
        )

    def test_methodology_portal_link_resolves_an_individual_before_dashboard(self):
        html = (STATIC / "about.html").read_text(encoding="utf-8")
        script = (STATIC / "about.js").read_text(encoding="utf-8")

        self.assertIn('id="sidebar-breast-portal"', html)
        self.assertIn('src="/static/about.js?v=2"', html)
        self.assertIn('fetch("/api/individuals?cohort=1000_genomes")', script)
        self.assertIn("individual_id: individualId", script)
        self.assertIn('disease: "breast_cancer"', script)

    def test_selected_individual_is_shared_across_primary_pages(self):
        for filename in ("home.js", "dashboard.js", "about.js"):
            with self.subTest(filename=filename):
                script = (STATIC / filename).read_text(encoding="utf-8")
                self.assertIn('INDIVIDUAL_PREFERENCE_KEY = "xprs.individual_id"', script)

        dashboard_script = (STATIC / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn(
            'readPreference(INDIVIDUAL_PREFERENCE_KEY, "")',
            dashboard_script,
        )


if __name__ == "__main__":
    unittest.main()
