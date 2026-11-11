"""Persist server logs to a rotating file.

The portal previously logged only to the console (a tmux pane with limited
scrollback), so failures such as empty LLM completions could not be traced
after the fact.

Privacy: K-PREDICT chat sessions are intentionally kept in memory only.
INFO-level lines include clinicians' question text and pseudonymous IDs in
request URLs, so the file defaults to WARNING and above (failures, fallbacks,
retries), and every line written to the file, including tracebacks, passes
through the K-PREDICT sanitizer. Set SERVER_LOG_FILE_LEVEL=INFO for a
debugging session when fuller detail is needed.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from llm_utils import sanitize_kpredict_text

LOG_FILE_NAME = "xprs_portal.log"
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_HANDLER_NAME = "xprs_server_file"


class RedactingFormatter(logging.Formatter):
    """Format normally, then strip identifiers before the line reaches disk.

    Redacting at format time (not by mutating the record) leaves console
    output unchanged.
    """

    def format(self, record: logging.LogRecord) -> str:
        return sanitize_kpredict_text(super().format(record))


def configure_file_logging(log_dir: Path, level_name: str | None = None) -> Path:
    """Attach a redacting rotating file handler to the root and uvicorn loggers.

    Returns the log file path. Calling it twice does not add a second handler.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(log_dir, 0o700)  # pseudonymous cohort context; owner-only
    log_path = log_dir / LOG_FILE_NAME

    level = logging.getLevelName((level_name or "WARNING").upper())
    if not isinstance(level, int):
        level = logging.WARNING

    if any(existing.get_name() == _HANDLER_NAME for existing in logging.getLogger().handlers):
        return log_path  # already configured; do not open a second file handle

    handler = RotatingFileHandler(log_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
    handler.set_name(_HANDLER_NAME)
    handler.setLevel(level)
    handler.setFormatter(RedactingFormatter(LOG_FORMAT))

    # uvicorn's own loggers do not propagate to the root logger.
    for logger in (logging.getLogger(), logging.getLogger("uvicorn"), logging.getLogger("uvicorn.access")):
        if not any(existing.get_name() == _HANDLER_NAME for existing in logger.handlers):
            logger.addHandler(handler)
    return log_path
