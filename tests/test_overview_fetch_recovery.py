from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OverviewFetchRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (ROOT / "static" / "home.js").read_text(encoding="utf-8")
        cls.html = (ROOT / "static" / "home.html").read_text(encoding="utf-8")

    def test_overview_requests_retry_network_interruptions(self):
        self.assertIn("OVERVIEW_NETWORK_RETRY_DELAYS_MS = [0, 400, 1200]", self.script)
        self.assertIn("fetchJSONWithNetworkRetry", self.script)
        self.assertIn("error instanceof TypeError", self.script)
        self.assertIn("error?.isHttpError", self.script)

    def test_selection_changes_ignore_stale_overview_responses(self):
        self.assertIn("let diseaseOverviewRequestId = 0", self.script)
        self.assertIn("requestId !== diseaseOverviewRequestId", self.script)
        self.assertIn("pid !== selectedIndividualId", self.script)

    def test_home_script_cache_version_was_bumped(self):
        self.assertIn('/static/home.js?v=44', self.html)


if __name__ == "__main__":
    unittest.main()
