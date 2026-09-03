from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config import DATA_DIR, GENE_IMPORTANCE_CSV, OT_MERGED_CSV, PLOT_DATA_CACHE_DIR


DEFAULT_DISEASE_SLUG = "breast_cancer"


@dataclass(frozen=True)
class DiseaseConfig:
    slug: str
    display_name: str
    short_label: str
    icon: str
    primary_phenotype: str
    enabled: bool
    gene_importance_csv: Path
    plot_cache_dir: Path
    ot_merged_csv: Path
    opentargets_disease_id: str | None = None
    unavailable_reason: str | None = None

    def public_dict(self) -> dict:
        return {
            "slug": self.slug,
            "display_name": self.display_name,
            "short_label": self.short_label,
            "icon": self.icon,
            "primary_phenotype": self.primary_phenotype,
            "enabled": self.enabled,
            "opentargets_disease_id": self.opentargets_disease_id,
            "unavailable_reason": self.unavailable_reason,
        }


def _unavailable_disease(
    slug: str,
    display_name: str,
    short_label: str,
    icon: str,
    primary_phenotype: str,
) -> DiseaseConfig:
    return DiseaseConfig(
        slug=slug,
        display_name=display_name,
        short_label=short_label,
        icon=icon,
        primary_phenotype=primary_phenotype,
        enabled=False,
        gene_importance_csv=DATA_DIR / slug / "all_individuals_gene_importance.csv",
        plot_cache_dir=DATA_DIR / slug / "plot_cache",
        ot_merged_csv=DATA_DIR / slug / "ot_gene_associations.csv",
        opentargets_disease_id=None,
        unavailable_reason="XPRS model data are not configured for this disease yet.",
    )


# Insertion order is the display order on the disease overview page.
DISEASE_REGISTRY: dict[str, DiseaseConfig] = {
    "breast_cancer": DiseaseConfig(
        slug="breast_cancer",
        display_name="Breast Cancer",
        short_label="Breast",
        icon="vaccines",
        primary_phenotype="breast cancer",
        enabled=True,
        gene_importance_csv=GENE_IMPORTANCE_CSV,
        plot_cache_dir=PLOT_DATA_CACHE_DIR,
        ot_merged_csv=OT_MERGED_CSV,
        opentargets_disease_id="EFO_0000305",
    ),
    "type2_diabetes": _unavailable_disease(
        "type2_diabetes", "Type 2 Diabetes", "T2D", "medication", "type 2 diabetes"
    ),
    "gastric_cancer": _unavailable_disease(
        "gastric_cancer", "Gastric Cancer", "Gastric", "gastroenterology", "gastric cancer"
    ),
    "colorectal_cancer": _unavailable_disease(
        "colorectal_cancer", "Colorectal Cancer", "Colorectal", "gastroenterology", "colorectal cancer"
    ),
    "uterine_cancer": _unavailable_disease(
        "uterine_cancer", "Uterine Cancer", "Uterine", "gynecology", "uterine cancer"
    ),
    "thyroid_cancer": _unavailable_disease(
        "thyroid_cancer", "Thyroid Cancer", "Thyroid", "endocrinology", "thyroid cancer"
    ),
    "prostate_cancer": _unavailable_disease(
        "prostate_cancer", "Prostate Cancer", "Prostate", "urology", "prostate cancer"
    ),
    "pancreatic_cancer": _unavailable_disease(
        "pancreatic_cancer", "Pancreatic Cancer", "Pancreatic", "gastroenterology", "pancreatic cancer"
    ),
}


def normalize_disease_slug(slug: str | None) -> str:
    return (slug or DEFAULT_DISEASE_SLUG).strip() or DEFAULT_DISEASE_SLUG


def get_disease_config(slug: str | None = None) -> DiseaseConfig:
    normalized = normalize_disease_slug(slug)
    if normalized not in DISEASE_REGISTRY:
        valid = ", ".join(DISEASE_REGISTRY)
        raise ValueError(f"Unknown disease '{normalized}'. Expected one of: {valid}.")
    return DISEASE_REGISTRY[normalized]


def enabled_disease_config(slug: str | None = None) -> DiseaseConfig:
    config = get_disease_config(slug)
    if not config.enabled:
        reason = config.unavailable_reason or "This disease is not enabled yet."
        raise ValueError(f"{config.display_name} is not available yet. {reason}")
    return config


def list_diseases() -> list[DiseaseConfig]:
    return list(DISEASE_REGISTRY.values())
