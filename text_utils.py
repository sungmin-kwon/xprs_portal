from __future__ import annotations

import logging
import math
import re
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


def infer_output_language(text: str | None, fallback: str | None = "en") -> str:
    """Choose a response language from the current turn when it is clear.

    Explicit language instructions take precedence, followed by the writing
    system used in the question. Inputs without natural-language evidence
    (for example ``KCNQ1?``) retain the dashboard/session language.
    """
    value = str(text or "").strip()
    default = normalize_output_language(fallback)
    if not value:
        return default

    if re.search(r"\b(?:in|into)\s+korean\b|\bkorean\s+(?:answer|response|version)\b", value, re.I) \
            or re.search(r"(?:한국어|한글)(?:로|으로)\s*(?:답|설명|작성|말)", value):
        return "ko"
    if re.search(r"\b(?:in|into)\s+english\b|\benglish\s+(?:answer|response|version)\b", value, re.I) \
            or re.search(r"영어(?:로|으로)\s*(?:답|설명|작성|말)", value):
        return "en"
    if re.search(r"[가-힣ㄱ-ㅎㅏ-ㅣ]", value):
        return "ko"
    if re.search(r"\b[a-z]{2,}\b", value, re.I):
        return "en"
    return default


UNANNOTATED_REGION_PREFIX = "Unannotated region"
_PLACEHOLDER_REGION_SYMBOL = re.compile(r"^NA(?:_\d+)?$")


def unannotated_region_label(chromosome: Any, start: Any, end: Any) -> str:
    """Readable label for an XPRS window that has no gene symbol (``NA_n`` rows).

    ``NA_n`` numbering is per disease model, so ``NA_1`` names different
    windows in different models; coordinates make the label unambiguous.

    The colon-free ``chr12 115.19–115.59 Mb`` form is deliberate: these are
    model-level 400 kb window bounds shared by every individual, not variant
    positions, and the ``chrN:position`` form would be stripped by the
    K-PREDICT variant-coordinate sanitizer in ``llm_utils``.
    """
    return (
        f"{UNANNOTATED_REGION_PREFIX} chr{chromosome} "
        f"{float(start) / 1e6:.2f}–{float(end) / 1e6:.2f} Mb"
    )


def is_unannotated_region(name: str | None) -> bool:
    """True for placeholder ``NA_n`` symbols and their relabeled form.

    Such regions have no gene symbol to search for: querying literature
    providers for ``NA_1`` returned unrelated materials-science papers.
    """
    text = str(name or "").strip()
    return bool(_PLACEHOLDER_REGION_SYMBOL.match(text)) or text.startswith(UNANNOTATED_REGION_PREFIX)


def format_contribution(value: float, significant_digits: int = 3) -> str:
    """Format a gene contribution score without rounding small values to zero.

    Contributions span several orders of magnitude, and fixed two-decimal
    formatting showed many risk-lowering genes as 0.00 (clinician feedback #11).
    Values are shown to ``significant_digits`` significant figures, switching to
    compact scientific notation (e.g. ``3.21e-4``) below 0.001.
    """
    value = float(value)
    if value == 0.0 or not math.isfinite(value):
        return "0" if value == 0.0 else str(value)
    if abs(value) < 1e-3:
        mantissa, exponent = f"{value:.{significant_digits - 1}e}".split("e")
        return f"{mantissa}e{int(exponent)}"
    return f"{value:.{significant_digits}g}"


def ui_label(language: str | None, key: str, **kwargs: Any) -> str:
    lang = normalize_output_language(language)
    template = LANGUAGE_LABELS.get(lang, LANGUAGE_LABELS.get("en", {})).get(key, "")
    return template.format(**kwargs) if kwargs else template
