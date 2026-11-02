from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import requests

from agents.rag import acquire_chroma_process_lock
from agents.semantic_scholar import SemanticScholarAgent, parse_retry_after_seconds


class FakeResponse:
    def __init__(self, status_code, data=None, text="error", headers=None):
        self.status_code = status_code
        self._data = data or {"data": []}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._data


class SemanticScholarRuntimeTests(unittest.TestCase):
    @staticmethod
    def make_agent():
        agent = SemanticScholarAgent(api_key="test", cache_dir=None)
        agent._respect_api_key_rate_limit = lambda *_args, **_kwargs: None
        return agent

    @patch("agents.semantic_scholar.time.sleep", return_value=None)
    @patch("agents.semantic_scholar.requests.get")
    def test_429_stops_retries_and_preserves_retry_after(self, mock_get, sleep):
        mock_get.return_value = FakeResponse(429, headers={"Retry-After": "37"})
        agent = self.make_agent()
        self.assertIsNone(agent.search("TP53", max_retries=5))
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(agent.get_health_status()["last_retry_after_seconds"], 37.0)
        sleep.assert_not_called()

    @patch("agents.semantic_scholar.time.sleep", return_value=None)
    @patch("agents.semantic_scholar.requests.get")
    def test_server_error_retries_and_recovers(self, mock_get, _sleep):
        mock_get.side_effect = [
            FakeResponse(500),
            FakeResponse(200, data={"data": [{"paperId": "ok"}]}),
        ]
        self.assertEqual(self.make_agent().search("TP53", max_retries=3)[0]["paperId"], "ok")
        self.assertEqual(mock_get.call_count, 2)

    @patch("agents.semantic_scholar.time.sleep", return_value=None)
    @patch("agents.semantic_scholar.requests.get")
    def test_read_timeout_is_not_retried(self, mock_get, sleep):
        mock_get.side_effect = requests.ReadTimeout("read timed out")
        self.assertIsNone(self.make_agent().search("TP53", max_retries=5, timeout=45))
        self.assertEqual(mock_get.call_count, 1)
        sleep.assert_not_called()

    def test_retry_after_supports_http_date(self):
        now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(
            parse_retry_after_seconds("Mon, 31 Aug 2026 12:02:00 GMT", now=now),
            120.0,
        )

    @patch("agents.semantic_scholar.requests.get")
    def test_manual_key_probe_distinguishes_invalid_and_rate_limited(self, mock_get):
        mock_get.return_value = FakeResponse(403, text="forbidden")
        invalid = self.make_agent().probe_api_key()
        self.assertEqual(invalid["status"], "invalid")
        self.assertEqual(invalid["query"], "human genetics")
        mock_get.return_value = FakeResponse(429)
        self.assertEqual(self.make_agent().probe_api_key()["status"], "rate_limited")

    @patch("agents.semantic_scholar.requests.get")
    def test_key_probe_does_not_replace_pool_specific_attempt(self, mock_get):
        agent = self.make_agent()
        agent._update_status(last_status_code=429, last_error="rate limited")
        agent._record_cached_query_request("TP53", None, succeeded=False)

        mock_get.return_value = FakeResponse(200, data={"data": []})
        self.assertEqual(agent.probe_api_key()["status"], "ok")

        attempt = agent.get_query_attempts()[0]
        self.assertEqual(attempt["gene"], "TP53")
        self.assertEqual(attempt["outcome"], "rate_limited")
        self.assertEqual(attempt["http_status"], 429)

    def test_chroma_process_lock_rejects_a_second_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            first = acquire_chroma_process_lock(directory)
            try:
                with self.assertRaisesRegex(RuntimeError, "already open"):
                    acquire_chroma_process_lock(directory)
            finally:
                first.close()


if __name__ == "__main__":
    unittest.main()
