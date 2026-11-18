"""Security invariants that hold across whole pages or routers.

These are the only tests that read front-end source text, and only for rules
that must hold everywhere (not for particular labels, selectors, or layouts).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import kpredict, pages
from tests.support import STATIC

TOKEN_HEADER = "X-XPRS-KPREDICT-Token"
NOT_FOUND = {"detail": "Not found"}


def dummy_query_params(route) -> dict[str, str]:
    """Fill required query parameters so FastAPI validation (422) does not
    run before the access check."""
    return {
        param.name: "1" if param.field_info.annotation in (int, float) else "x"
        for param in route.dependant.query_params
        if param.field_info.is_required()
    }


class KPredictRouteAccessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        (root / "manifest.json").write_text(json.dumps({"diseases": []}))
        self.environment = patch.dict(os.environ, {
            "KPREDICT_ENABLED": "true",
            "KPREDICT_DATA_ROOT": str(root),
            "XPRS_KPREDICT_TOKEN": "cohort-secret",
            "XPRS_ADMIN_TOKEN": "admin-secret",
        })
        self.environment.start()
        app = FastAPI()
        app.include_router(kpredict.router)
        self.app = app
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    def test_every_private_data_route_hides_itself_without_a_token(self):
        routes = [
            route for route in self.app.routes
            if getattr(route, "path", "").startswith("/api/kpredict/")
            and "GET" in getattr(route, "methods", ())
        ]
        self.assertGreater(len(routes), 0)

        for route in routes:
            with self.subTest(path=route.path):
                params = dummy_query_params(route)
                anonymous = self.client.get(route.path, params=params)
                self.assertEqual(anonymous.status_code, 404)
                self.assertEqual(anonymous.json(), NOT_FOUND)

                # With a valid token the request must get past the access
                # check; otherwise the 404 above would prove nothing.
                authorized = self.client.get(
                    route.path, params=params, headers={TOKEN_HEADER: "cohort-secret"}
                )
                passed_check = authorized.status_code != 404 or authorized.json() != NOT_FOUND
                self.assertTrue(passed_check, authorized.text)


class PageResponseTests(unittest.TestCase):
    def test_html_pages_are_not_cached_across_deployments(self):
        app = FastAPI()
        app.include_router(pages.router)
        client = TestClient(app)
        for path in ("/", "/dashboard", "/about", "/cohort-analysis"):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response.headers["cache-control"])


class StaticSourceInvariantTests(unittest.TestCase):
    def test_new_tab_links_send_no_referrer(self):
        # Portal URLs can carry pseudonymous individual IDs; a Referer header
        # would hand them to ClinVar, journal sites, etc. rel="noreferrer"
        # also implies noopener.
        sources = sorted(STATIC.glob("*.html")) + sorted(STATIC.glob("*.js"))
        checked = 0
        for path in sources:
            text = path.read_text(encoding="utf-8")
            # Anchor markup in HTML or JS template strings.
            for match in re.finditer(r"<a\b[^>]*\btarget=\"_blank\"[^>]*>", text):
                checked += 1
                with self.subTest(file=path.name, tag=match.group(0)[:80]):
                    self.assertRegex(match.group(0), r'\brel="[^"]*\bnoreferrer\b')
            # Anchors built with DOM properties: link.target = "_blank"; link.rel = ...
            for line in text.splitlines():
                if re.search(r"\.target\s*=\s*\"_blank\"", line):
                    checked += 1
                    with self.subTest(file=path.name, line=line.strip()[:80]):
                        self.assertRegex(line, r"\.rel\s*=\s*\"[^\"]*\bnoreferrer\b")
        self.assertGreater(checked, 0)

    def test_external_scripts_are_pinned_to_a_version(self):
        # An unversioned CDN URL (e.g. .../npm/marked/marked.min.js) runs
        # whatever the CDN serves that day inside the logged-in page.
        # Prefer serving libraries from static/vendor/.
        for path in sorted(STATIC.glob("*.html")):
            text = path.read_text(encoding="utf-8")
            for src in re.findall(r'<script\b[^>]*\bsrc="(https?://[^"]+)"', text):
                with self.subTest(file=path.name, src=src):
                    self.assertRegex(src, r"\d+\.\d+\.\d+")


if __name__ == "__main__":
    unittest.main()
