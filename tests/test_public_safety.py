from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

import session_logs
from routes.admin_documents import _require_admin_access


def request_with_admin_token(token: str | None = None) -> Request:
    headers = []
    if token is not None:
        headers.append((b"x-xprs-admin-token", token.encode("utf-8")))
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/admin/documents",
        "root_path": "",
        "scheme": "http",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 9009),
    })


class AdminAccessTests(unittest.TestCase):
    def test_admin_route_is_disabled_when_token_is_unset(self):
        with patch.dict(os.environ, {"XPRS_ADMIN_TOKEN": ""}):
            with self.assertRaises(HTTPException) as raised:
                _require_admin_access(request_with_admin_token())
        self.assertEqual(raised.exception.status_code, 404)

    def test_admin_route_accepts_the_configured_token(self):
        with patch.dict(os.environ, {"XPRS_ADMIN_TOKEN": "test-admin-token"}):
            _require_admin_access(request_with_admin_token("test-admin-token"))


class EphemeralSessionTests(unittest.TestCase):
    def setUp(self):
        with session_logs._MEMORY_SESSIONS_LOCK:
            session_logs._MEMORY_SESSIONS.clear()

    def tearDown(self):
        with session_logs._MEMORY_SESSIONS_LOCK:
            session_logs._MEMORY_SESSIONS.clear()

    def test_nonpersistent_session_remains_available_in_process(self):
        payload = session_logs.load_session_log("PUBLIC_TEST", "session-one")
        payload["simple_summary"] = "ephemeral summary"

        with patch.object(session_logs, "SESSION_LOGGING_ENABLED", False):
            session_logs.maybe_save_session_log("PUBLIC_TEST", "session-one", payload)

        restored = session_logs.load_session_log_by_id(
            "session-one",
            individual_id="PUBLIC_TEST",
        )
        self.assertEqual(restored["simple_summary"], "ephemeral summary")

    def test_ephemeral_store_evicts_the_oldest_session(self):
        with (
            patch.object(session_logs, "SESSION_LOGGING_ENABLED", False),
            patch.object(session_logs, "EPHEMERAL_SESSION_LIMIT", 2),
        ):
            for number in range(3):
                session_logs.maybe_save_session_log(
                    "PUBLIC_TEST",
                    f"session-{number}",
                    {"session_id": f"session-{number}", "individual_id": "PUBLIC_TEST"},
                )

        self.assertIsNone(session_logs._load_memory_session("PUBLIC_TEST", "session-0"))
        self.assertIsNotNone(session_logs._load_memory_session("PUBLIC_TEST", "session-2"))


if __name__ == "__main__":
    unittest.main()
