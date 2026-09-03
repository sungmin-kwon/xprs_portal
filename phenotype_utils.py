import re
from functools import lru_cache

from config import GENERIC_PHENOTYPES, PHENOTYPE_ALIASES, PHENOTYPE_LABELS_KO
from text_utils import unique_preserving_order


def _looks_like_low_information_label(original: str, normalized: str) -> bool:
    if not normalized:
        return True
    if re.fullmatch(r"[a-z0-9]{1,4}", normalized):
        return True
    raw = (original or "").strip()
    if raw and re.fullmatch(r"[A-Z0-9-]{1,6}", raw):
        return True
    return False


def _normalize_matching_text(text: str) -> str:
    normalized = (text or "").lower()
    normalized = normalized.replace("’", "'").replace("‐", "-").replace("–", "-").replace("—", "-")
    normalized = normalized.replace("/", " ").replace("_", " ")
    normalized = re.sub(r"['.`]", "", normalized)
    normalized = re.sub(r"[^\w+\-\s]", " ", normalized, flags=re.UNICODE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _generate_alias_variants(term: str) -> set[str]:
    raw = (term or "").strip().lower()
    if not raw:
        return set()

    variants = {raw}
    variants.add(raw.replace("’", "'"))
    variants.add(raw.replace(" type ii ", " type 2 "))
    variants.add(raw.replace(" type iii ", " type 3 "))
    variants.add(raw.replace(" type iv ", " type 4 "))
    variants.add(raw.replace(" type vi ", " type 6 "))
    variants.add(raw.replace(" type vii ", " type 7 "))
    variants.add(raw.replace(" type viii ", " type 8 "))
    variants.add(raw.replace(" type ix ", " type 9 "))
    variants.add(raw.replace(" type i ", " type 1 "))
    variants.add(raw.replace(" type v ", " type 5 "))
    variants.add(raw.replace("type ii", "type 2"))
    variants.add(raw.replace("type iii", "type 3"))
    variants.add(raw.replace("type iv", "type 4"))
    variants.add(raw.replace("type vi", "type 6"))
    variants.add(raw.replace("type vii", "type 7"))
    variants.add(raw.replace("type viii", "type 8"))
    variants.add(raw.replace("type ix", "type 9"))
    variants.add(raw.replace("type i", "type 1"))
    variants.add(raw.replace("type v", "type 5"))
    variants.add(raw.replace("-", " "))
    variants.add(raw.replace("'", ""))
    return {variant.strip() for variant in variants if variant.strip()}


@lru_cache(maxsize=1)
def _compiled_aliases() -> list[tuple[str, list[str]]]:
    compiled: list[tuple[str, list[str]]] = []
    for canonical, aliases in PHENOTYPE_ALIASES.items():
        normalized_aliases = {
            _normalize_matching_text(candidate)
            for alias in [canonical, *(aliases or []), PHENOTYPE_LABELS_KO.get(canonical, "")]
            for candidate in _generate_alias_variants(alias)
        }
        normalized_aliases = {alias for alias in normalized_aliases if alias and alias not in GENERIC_PHENOTYPES}
        for alias in normalized_aliases:
            compiled.append((alias, [canonical]))

    compiled.sort(key=lambda item: (-len(item[0]), item[0]))

    merged: dict[str, list[str]] = {}
    for alias, canonicals in compiled:
        merged.setdefault(alias, [])
        merged[alias].extend(canonicals)

    return [
        (alias, unique_preserving_order(canonicals))
        for alias, canonicals in merged.items()
    ]


def text_matches_alias(text: str, alias: str) -> bool:
    normalized_text = _normalize_matching_text(text)
    normalized_alias = _normalize_matching_text(alias)
    if not normalized_alias:
        return False
    return bool(re.search(rf"(?<!\w){re.escape(normalized_alias)}(?!\w)", normalized_text))


def infer_phenotypes_from_text(text: str) -> list[str]:
    normalized_text = _normalize_matching_text(text)
    if not normalized_text:
        return []

    hits: list[str] = []
    for alias, canonicals in _compiled_aliases():
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized_text):
            hits.extend(canonicals)
    return unique_preserving_order(hits)


def canonicalize_phenotype_value(value: str) -> list[str]:
    normalized = _normalize_matching_text(value)
    if not normalized or normalized in GENERIC_PHENOTYPES:
        return []

    exact_hits: list[str] = []
    for alias, canonicals in _compiled_aliases():
        if normalized == alias:
            exact_hits.extend(canonicals)
    if exact_hits:
        return unique_preserving_order(exact_hits)

    inferred = infer_phenotypes_from_text(value)
    if inferred:
        return inferred

    if _looks_like_low_information_label(value, normalized):
        return []

    return []


def normalize_phenotype_values(values: list[str]) -> list[str]:
    normalized_hits: list[str] = []
    for value in values:
        normalized_hits.extend(canonicalize_phenotype_value(value))
    return unique_preserving_order(normalized_hits)
