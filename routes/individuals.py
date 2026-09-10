import logging
import os

import pandas as pd
from fastapi import APIRouter, Query, Request

from cohort_registry import get_cohort_config
from disease_registry import get_disease_config, list_diseases
router = APIRouter()


def _individual_ids_from_csv(path) -> list[str]:
    try:
        columns = pd.read_csv(path, nrows=0).columns
    except Exception as e:
        logging.warning("Failed to read individual IDs from %s: %s", path, e)
        return []
    return [c for c in columns if c != "Gene"]


@router.get("/api/individuals")
async def list_individuals(
    request: Request,
    disease: str | None = Query(default=None),
    cohort: str | None = Query(default=None),
):
    try:
        cohort_config = get_cohort_config(cohort)
    except ValueError:
        return {"individuals": [], "cohort": cohort, "enabled": False, "unavailable_reason": "Unknown cohort."}

    if not cohort_config.data_available:
        return {
            "individuals": [],
            "cohort": cohort_config.slug,
            "enabled": False,
            "unavailable_reason": cohort_config.unavailable_reason,
        }

    if disease:
        try:
            config = get_disease_config(disease)
        except ValueError:
            return {
                "individuals": [],
                "disease": disease,
                "cohort": cohort_config.slug,
                "enabled": False,
            }
        if not config.enabled:
            return {
                "individuals": [],
                "disease": config.slug,
                "cohort": cohort_config.slug,
                "enabled": False,
                "unavailable_reason": config.unavailable_reason,
            }
        return {
            "individuals": _individual_ids_from_csv(config.gene_importance_csv),
            "disease": config.slug,
            "cohort": cohort_config.slug,
            "enabled": True,
        }

    individual_ids = getattr(request.app.state, "individual_ids_union", None)
    if individual_ids is None:
        ids: list[str] = []
        for config in list_diseases():
            if not config.enabled:
                continue
            ids.extend(_individual_ids_from_csv(config.gene_importance_csv))
        individual_ids = sorted(set(ids))
        request.app.state.individual_ids_union = individual_ids
    return {"individuals": individual_ids, "cohort": cohort_config.slug, "enabled": True}


@router.get("/api/info")
def get_app_info():
    # Report the model the running agents actually resolved to (the source of
    # truth), falling back to env vars only if the runtime hasn't loaded it.
    from runtime_agents import get_runtime_agents

    runtime_model = get_runtime_agents().get("llm_model")
    return {
        "model": runtime_model
        or os.getenv("LLM_MODEL")
        or os.getenv("MODEL")
        or "AI",
        "evaluation_enabled": bool(os.getenv("XPRS_EVALUATION_TOKEN", "").strip()),
    }
