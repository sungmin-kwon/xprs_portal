from __future__ import annotations

from dataclasses import dataclass


DEFAULT_COHORT_SLUG = "1000_genomes"


@dataclass(frozen=True)
class CohortConfig:
    slug: str
    name: str
    access: str
    data_available: bool
    unavailable_reason: str | None = None

    @property
    def display_label(self) -> str:
        return f"{self.name} ({self.access})"

    def public_dict(self) -> dict:
        return {
            "slug": self.slug,
            "name": self.name,
            "access": self.access,
            "display_label": self.display_label,
            "data_available": self.data_available,
            "unavailable_reason": self.unavailable_reason,
        }


COHORT_REGISTRY: dict[str, CohortConfig] = {
    "1000_genomes": CohortConfig(
        slug="1000_genomes",
        name="1000 Genomes",
        access="public",
        data_available=True,
    ),
    "kpredict": CohortConfig(
        slug="kpredict",
        name="K-PREDICT",
        access="private",
        data_available=False,
        unavailable_reason="K-PREDICT data are available only in a configured private deployment.",
    ),
}

COHORT_ALIASES = {
    "kfda": "kpredict",
}


def get_cohort_config(slug: str | None = None) -> CohortConfig:
    normalized = (slug or DEFAULT_COHORT_SLUG).strip() or DEFAULT_COHORT_SLUG
    normalized = COHORT_ALIASES.get(normalized, normalized)
    if normalized not in COHORT_REGISTRY:
        valid = ", ".join(COHORT_REGISTRY)
        raise ValueError(f"Unknown cohort '{normalized}'. Expected one of: {valid}.")
    return COHORT_REGISTRY[normalized]


def list_cohorts() -> list[CohortConfig]:
    return list(COHORT_REGISTRY.values())
