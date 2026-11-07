from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
