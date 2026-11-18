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


# Overview grouping for the continuous-trait PRS. The order follows Dr. Kim's
# cohort_summary.tsv, which already lists the traits by clinical panel; the
# group names are ours (draft, to be confirmed). Unknown trait IDs fall into
# "other" so a new trait still appears.
TRAIT_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("lipids", ("TC", "TG", "HDLC", "LDLC")),
    ("glucose", ("Glucose", "HbA1c")),
    ("blood_pressure", ("SBP", "DBP", "MAP", "PP")),
    ("body_size", ("BMI", "Height", "BW")),
    ("kidney", ("sCr", "eGFR", "BUN", "UA")),
    ("liver", ("ALT", "AST", "ALP", "GGT", "TBil", "Alb", "TP", "AG", "NAP")),
    ("blood_count", ("WBC", "Neutro", "Lym", "Mono", "Eosino", "Baso", "Plt", "RBC", "Hb", "Ht", "MCV", "MCH", "MCHC")),
    ("minerals_inflammation", ("Ca", "P", "CRP")),
)
