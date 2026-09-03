from fastapi import APIRouter

import config

router = APIRouter()


@router.get("/api/models")
def get_models():
    """Curated model allowlists backing the model-switching dropdowns. Reference
    extraction is included read-only so the future dropdown is a frontend-only add."""
    return {
        "generation": config.GENERATION_MODELS,
        "reference_extraction": config.REFERENCE_EXTRACTION_MODELS,
        "default_generation": config.DEFAULT_GENERATION_MODEL,
        "default_reference_extraction": config.DEFAULT_REFERENCE_EXTRACTION_MODEL,
        "cost_cap_per_million": config.MODEL_COST_CAP_PER_MILLION,
    }
