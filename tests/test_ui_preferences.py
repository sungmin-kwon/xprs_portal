import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class UiPreferenceTests(unittest.TestCase):
    def test_landing_page_has_theme_toggle_and_dark_palette(self):
        html = (STATIC / "home.html").read_text(encoding="utf-8")
        css = (STATIC / "home.css").read_text(encoding="utf-8")
        self.assertIn('id="theme-toggle-top"', html)
        self.assertIn("body.dark-theme", css)

    def test_landing_and_dashboard_use_the_same_preference_keys(self):
        for filename in ("home.js", "dashboard.js"):
            with self.subTest(filename=filename):
                script = (STATIC / filename).read_text(encoding="utf-8")
                self.assertIn('LANGUAGE_PREFERENCE_KEY = "xprs.language"', script)
                self.assertIn('THEME_PREFERENCE_KEY = "xprs.theme"', script)
                self.assertIn("window.localStorage.getItem", script)
                self.assertIn("window.localStorage.setItem", script)

    def test_dashboard_no_longer_forces_light_and_english_defaults(self):
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

    def test_third_visualization_is_reserved_for_rare_variants(self):
        html = (STATIC / "dashboard.html").read_text(encoding="utf-8")
        script = (STATIC / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn('data-i18n="rareVariantTitle"', html)
        self.assertIn('data-i18n="rareVariantUnavailable"', html)
        self.assertIn('rareVariantTitle: "희귀 변이 분석"', script)
        self.assertNotIn("Visualization Placeholder", html)
        self.assertNotIn("Reserved for future analysis panel", html)

    def test_unavailable_cohort_message_is_consistent_and_plain(self):
        script = (STATIC / "home.js").read_text(encoding="utf-8")

        self.assertIn('cohortDataUnavailable: "No data available for this cohort."', script)
        self.assertIn('cohortDataUnavailable: "이 코호트에는 사용할 수 있는 데이터가 없습니다."', script)
        self.assertIn('if (cohort && !cohort.data_available) return t("cohortDataUnavailable");', script)
        self.assertNotIn("No XPRS model data are configured yet", script)
        self.assertNotIn("XPRS model data are not configured for this disease yet", script)


if __name__ == "__main__":
    unittest.main()
