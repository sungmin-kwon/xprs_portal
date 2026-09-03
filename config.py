import os
import json
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parent


def _resolve_path(value: str | None, default: Path) -> Path:
    raw = Path(value).expanduser() if value else default
    return raw if raw.is_absolute() else (REPO_DIR / raw).resolve()


APP_BASE_DIR = _resolve_path(os.getenv("APP_BASE_DIR"), REPO_DIR)
DATA_DIR = _resolve_path(os.getenv("DATA_DIR"), APP_BASE_DIR / "data")
RUNTIME_DIR = _resolve_path(os.getenv("RUNTIME_DIR"), APP_BASE_DIR)
STATIC_DIR = _resolve_path(os.getenv("STATIC_DIR"), APP_BASE_DIR / "static")
REF_DIR = _resolve_path(os.getenv("REF_DIR"), APP_BASE_DIR / "ref")

PLOTS_DIR = _resolve_path(os.getenv("PLOTS_DIR"), STATIC_DIR / "plots")
LOG_DIR = _resolve_path(os.getenv("LOG_DIR"), RUNTIME_DIR / "logs")
S2_CACHE_DIR = _resolve_path(os.getenv("S2_CACHE_DIR"), RUNTIME_DIR / "cache_s2")
CHROMA_DIR = _resolve_path(os.getenv("CHROMA_DIR"), RUNTIME_DIR / "chroma")
PLOT_DATA_CACHE_DIR = _resolve_path(os.getenv("PLOT_DATA_CACHE_DIR"), DATA_DIR / "plot_cache")
PHENOTYPE_ALIASES_JSON = _resolve_path(
    os.getenv("PHENOTYPE_ALIASES_JSON"),
    APP_BASE_DIR / "phenotype_aliases.json",
)
LANGUAGE_LABELS_JSON = _resolve_path(
    os.getenv("LANGUAGE_LABELS_JSON"),
    APP_BASE_DIR / "language_labels.json",
)
MODELS_JSON = _resolve_path(
    os.getenv("MODELS_JSON"),
    APP_BASE_DIR / "models.json",
)

GENE_IMPORTANCE_CSV = _resolve_path(
    os.getenv("GENE_IMPORTANCE_CSV"),
    DATA_DIR / "all_individuals_gene_importance.csv",
)
OT_MERGED_CSV = _resolve_path(
    os.getenv("OT_MERGED_CSV"),
    DATA_DIR / "ot_breast_carcinoma_gene_associations.csv",
)

SESSION_LOGGING_ENABLED = os.getenv("SESSION_LOGGING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
EPHEMERAL_SESSION_LIMIT = max(1, int(os.getenv("EPHEMERAL_SESSION_LIMIT", "100")))

RERANKER_ENABLED = os.getenv("RERANKER_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "ncbi/MedCPT-Cross-Encoder")
RERANKER_CANDIDATE_K = max(10, int(os.getenv("RERANKER_CANDIDATE_K", "30")))
RERANKER_BATCH_SIZE = max(1, int(os.getenv("RERANKER_BATCH_SIZE", "8")))
RERANKER_MAX_LENGTH = max(128, int(os.getenv("RERANKER_MAX_LENGTH", "512")))

with open(PHENOTYPE_ALIASES_JSON, "r", encoding="utf-8") as f:
    _PHENOTYPE_CONFIG = json.load(f)

with open(LANGUAGE_LABELS_JSON, "r", encoding="utf-8") as f:
    LANGUAGE_LABELS = json.load(f)

with open(MODELS_JSON, "r", encoding="utf-8") as f:
    _MODEL_CONFIG = json.load(f)

# Curated OpenRouter allowlists backing the model-switching dropdowns.
GENERATION_MODELS = _MODEL_CONFIG.get("generation", [])
REFERENCE_EXTRACTION_MODELS = _MODEL_CONFIG.get("reference_extraction", [])
MODEL_COST_CAP_PER_MILLION = _MODEL_CONFIG.get("cost_cap_per_million", {})

# Flat id sets for request validation (reject anything not on the allowlist).
GENERATION_MODEL_IDS = {m["id"] for m in GENERATION_MODELS}
REFERENCE_EXTRACTION_MODEL_IDS = {m["id"] for m in REFERENCE_EXTRACTION_MODELS}


def _default_model_id(models: list[dict]) -> str | None:
    for m in models:
        if m.get("default"):
            return m["id"]
    return models[0]["id"] if models else None


DEFAULT_GENERATION_MODEL = _default_model_id(GENERATION_MODELS)
DEFAULT_REFERENCE_EXTRACTION_MODEL = _default_model_id(REFERENCE_EXTRACTION_MODELS)

PHENOTYPE_ALIASES = {
    str(key): [str(item) for item in values]
    for key, values in (_PHENOTYPE_CONFIG.get("aliases") or {}).items()
}

GENERIC_PHENOTYPES = {
    str(item).lower()
    for item in (_PHENOTYPE_CONFIG.get("generic") or [])
}

PHENOTYPE_LABELS_KO = {
    str(key): str(value)
    for key, value in (_PHENOTYPE_CONFIG.get("ko_labels") or {}).items()
}


def ensure_runtime_dirs() -> None:
    for path in [PLOTS_DIR, LOG_DIR, S2_CACHE_DIR, CHROMA_DIR, PLOT_DATA_CACHE_DIR]:
        path.mkdir(parents=True, exist_ok=True)
