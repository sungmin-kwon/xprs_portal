from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from config import LANGUAGE_LABELS

logger = logging.getLogger(__name__)


def unique_preserving_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def emit_progress(callback: Optional[Callable[[str], None]], message: str) -> None:
    if not callback or not message:
        return
    try:
        callback(message)
    except Exception:
        pass


def format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


def emit_timing(
    callback: Optional[Callable[[str], None]],
    label: str,
    seconds: float,
    *,
    live: bool = True,
    min_seconds: float = 0.05,
    **details: Any,
) -> None:
    suffix = ""
    if details:
        rendered = ", ".join(f"{key}={value}" for key, value in details.items())
        suffix = f" ({rendered})"
    logger.info("[TIMING] %s: %s%s", label, format_duration(seconds), suffix)
    if live and seconds >= min_seconds:
        emit_progress(callback, f"{label}: {format_duration(seconds)}{suffix}")


def is_cancer_phenotype(phenotype: str) -> bool:
    normalized = (phenotype or "").strip().lower()
    return normalized.endswith("cancer") or normalized in {"glioblastoma"}


def normalize_output_language(language: str | None) -> str:
    return "ko" if str(language or "").lower().startswith("ko") else "en"


def ui_label(language: str | None, key: str, **kwargs: Any) -> str:
    lang = normalize_output_language(language)
    template = LANGUAGE_LABELS.get(lang, LANGUAGE_LABELS.get("en", {})).get(key, "")
    return template.format(**kwargs) if kwargs else template
