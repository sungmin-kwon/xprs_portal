from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request

from kpredict_access import has_kpredict_access


def request_with_header(name: str, value: str) -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(name.lower().encode(), value.encode())],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
    })


class KPredictAccessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "manifest.json").write_text(json.dumps({"diseases": []}))
        self.environment = patch.dict(os.environ, {
            "KPREDICT_ENABLED": "true",
            "KPREDICT_DATA_ROOT": str(self.root),
            "XPRS_KPREDICT_TOKEN": "cohort-secret",
            "XPRS_ADMIN_TOKEN": "admin-secret",
        })
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    def test_cohort_token_is_accepted(self):
        request = request_with_header("X-XPRS-KPREDICT-Token", "cohort-secret")
        self.assertTrue(has_kpredict_access(request))

    def test_admin_token_is_accepted_through_access_dialog_header(self):
        request = request_with_header("X-XPRS-KPREDICT-Token", "admin-secret")
        self.assertTrue(has_kpredict_access(request))

    def test_unknown_token_is_rejected(self):
        request = request_with_header("X-XPRS-KPREDICT-Token", "not-valid")
        self.assertFalse(has_kpredict_access(request))


if __name__ == "__main__":
    unittest.main()
