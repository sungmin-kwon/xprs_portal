"""Server log file: failures persist on disk, without chat content or identifiers."""
from __future__ import annotations

import logging
import stat
import tempfile
import unittest
from pathlib import Path

from server_logging import LOG_FILE_NAME, configure_file_logging


class ServerLoggingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.loggers = [logging.getLogger(), logging.getLogger("uvicorn"), logging.getLogger("uvicorn.access")]
        self.before = {id(lg): list(lg.handlers) for lg in self.loggers}
        self.root_level = logging.getLogger().level
        logging.getLogger().setLevel(logging.DEBUG)

    def tearDown(self):
        for lg in self.loggers:
            for handler in lg.handlers[:]:
                if handler not in self.before[id(lg)]:
                    lg.removeHandler(handler)
                    handler.close()
        logging.getLogger().setLevel(self.root_level)
        self.tmp.cleanup()

    def read_log(self, log_dir: Path) -> str:
        for lg in self.loggers:
            for handler in lg.handlers:
                handler.flush()
        return (log_dir / LOG_FILE_NAME).read_text(encoding="utf-8")

    def test_default_level_keeps_failures_and_drops_info(self):
        log_dir = Path(self.tmp.name) / "server"
        configure_file_logging(log_dir)
        logger = logging.getLogger("agents.explanation")

        logger.info("[FOLLOWUP_QUERY] question='Does this patient carry a variant?'")
        logger.warning("[LLM] model=test returned no completion; falling back")

        content = self.read_log(log_dir)
        self.assertIn("falling back", content)
        self.assertNotIn("FOLLOWUP_QUERY", content)
        self.assertEqual(stat.S_IMODE(log_dir.stat().st_mode), 0o700)

    def test_file_lines_are_redacted_including_tracebacks(self):
        log_dir = Path(self.tmp.name) / "server"
        configure_file_logging(log_dir, "INFO")
        logger = logging.getLogger("routes.chat")

        try:
            raise RuntimeError("failed for KP-ABCDEF123456 at rs1234567")
        except RuntimeError:
            logger.exception("Chat request failed for KP-ABCDEF123456")

        content = self.read_log(log_dir)
        self.assertIn("Chat request failed", content)
        self.assertIn("Traceback", content)
        self.assertNotIn("KP-ABCDEF123456", content)
        self.assertNotIn("rs1234567", content)

    def test_uvicorn_loggers_are_captured_and_handler_not_duplicated(self):
        log_dir = Path(self.tmp.name) / "server"
        configure_file_logging(log_dir)
        configure_file_logging(log_dir)

        logging.getLogger("uvicorn.error").error("worker crashed")

        self.assertIn("worker crashed", self.read_log(log_dir))
        root_file_handlers = [h for h in logging.getLogger().handlers if h.get_name() == "xprs_server_file"]
        self.assertEqual(len(root_file_handlers), 1)


if __name__ == "__main__":
    unittest.main()
