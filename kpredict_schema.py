from __future__ import annotations


# Source RDS/rare-finding disease identifiers do not always match the portal's
# public slugs. Keep the crosswalk in one dependency-light module so import,
# validation, and runtime grouping use the same interpretation.
SOURCE_DISEASE_TO_PORTAL: dict[str, str] = {
    "breast_cancer": "breast_cancer",
    "colorectal_cancer": "colorectal_cancer",
    "coronary_artery_disease": "coronary_artery_disease",
    "diabetes": "type2_diabetes",
    "gastric_cancer": "gastric_cancer",
    "myocardial_infarction": "myocardial_infarction",
    "pancreatic_cancer": "pancreatic_cancer",
    "prostate_cancer": "prostate_cancer",
    "thyroid_cancer": "thyroid_cancer",
    "uterine_cancer": "uterine_cancer",
}

PORTAL_DISEASE_ORDER: tuple[str, ...] = (
    "breast_cancer",
    "type2_diabetes",
    "gastric_cancer",
    "colorectal_cancer",
    "uterine_cancer",
    "thyroid_cancer",
    "prostate_cancer",
    "pancreatic_cancer",
    "coronary_artery_disease",
    "myocardial_infarction",
)


def normalize_kpredict_disease(value: object) -> str:
    disease = str(value or "").strip()
    return SOURCE_DISEASE_TO_PORTAL.get(disease, disease)
