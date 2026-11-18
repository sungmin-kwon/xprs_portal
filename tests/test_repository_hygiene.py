from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.check_public_repo import (
    PRIVATE_SOURCE_PATTERNS,
    _has_nonempty_secret_assignment,
    scan_repository,
)


class RepositoryHygieneTests(unittest.TestCase):
    def test_tracked_tree_contains_no_secrets_or_private_cohort_artifacts(self):
        self.assertEqual(scan_repository(), [])

    def test_private_cohort_token_assignment_is_treated_as_a_secret(self):
        self.assertTrue(
            _has_nonempty_secret_assignment(b"XPRS_KPREDICT_TOKEN=do-not-commit")
        )
        self.assertFalse(_has_nonempty_secret_assignment(b"XPRS_KPREDICT_TOKEN="))

    def test_real_looking_pseudonym_is_rejected_but_fixture_is_allowed(self):
        pseudonym_pattern = next(
            pattern
            for pattern, rule in PRIVATE_SOURCE_PATTERNS
            if rule == "K-PREDICT pseudonymous individual ID"
        )
        private_style_id = b"KP-" + b"D53760E01F00"
        self.assertIsNotNone(pseudonym_pattern.search(private_style_id))
        self.assertIsNone(pseudonym_pattern.search(b"KP-ABCDEF123456"))

    def test_deployment_specific_paths_and_hosts_are_rejected(self):
        patterns = {rule: pattern for pattern, rule in PRIVATE_SOURCE_PATTERNS}
        self.assertIsNotNone(
            patterns["deployment home path"].search(
                b"/data/" + b"home/example-user/xprs_portal"
            )
        )
        self.assertIsNotNone(
            patterns["deployment host IP"].search(
                b"http://" + b"192.0.2.10:9009/admin/documents"
            )
        )
        self.assertIsNone(
            patterns["deployment host IP"].search(
                b"http://127.0.0.1:9009/healthz"
            )
        )


    def _scan_temporary_repo(self, files: dict[str, bytes]) -> set[tuple[str, str]]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            for relative, payload in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            return {(finding.path, finding.rule) for finding in scan_repository(root)}

    def test_untracked_screenshot_fails_before_it_is_committed(self):
        # Regression for 2026-11-18: a portal screenshot in the repo root passed
        # because binary files were skipped. It is untracked here on purpose.
        png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        findings = self._scan_temporary_repo({"grouped_en.png": png, "static/logo.png": png})

        self.assertIn(("grouped_en.png", "image or document export outside static/"), findings)
        self.assertIn(("grouped_en.png", "binary file outside approved locations (cannot be scanned)"), findings)
        self.assertFalse({path for path, _ in findings} & {"static/logo.png"})

    def test_document_exports_and_unknown_binaries_fail_outside_approved_folders(self):
        findings = self._scan_temporary_repo({
            "reports/deck.pptx": b"PK\x03\x04\x00",
            "data/export.parquet": b"PAR1\x00\x00",
            "data/demo/plot_cache/full_prs.parquet": b"PAR1\x00\x00",
            "assets/fonts/Regular.ttf": b"\x00\x01\x00\x00",
        })

        self.assertIn(("reports/deck.pptx", "image or document export outside static/"), findings)
        self.assertIn(("data/export.parquet", "binary file outside approved locations (cannot be scanned)"), findings)
        self.assertFalse({path for path, _ in findings} & {"data/demo/plot_cache/full_prs.parquet", "assets/fonts/Regular.ttf"})

if __name__ == "__main__":
    unittest.main()
