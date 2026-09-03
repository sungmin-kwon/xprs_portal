from __future__ import annotations

import logging

from fastapi import APIRouter

from cohort_registry import get_cohort_config
from disease_registry import list_diseases
from plot_data import load_plot_data_store
from schemas import DiseaseRiskOverviewRequest

router = APIRouter()


@router.get("/api/diseases")
def get_diseases():
    return {"diseases": [config.public_dict() for config in list_diseases()]}


@router.post("/api/disease-risk-overview")
def disease_risk_overview(req: DiseaseRiskOverviewRequest):
    try:
        cohort = get_cohort_config(req.cohort)
    except ValueError:
        cohort = None

    if cohort is None or not cohort.data_available:
        reason = cohort.unavailable_reason if cohort else "Unknown cohort."
        return {
            "individual_id": req.individual_id,
            "cohort": cohort.public_dict() if cohort else None,
            "diseases": [
                {
                    **config.public_dict(),
                    "available_for_individual": False,
                    "density": None,
                    "unavailable_reason": reason,
                }
                for config in list_diseases()
            ],
        }

    cards = []
    for config in list_diseases():
        card = {
            **config.public_dict(),
            "available_for_individual": False,
            "density": None,
        }
        if not config.enabled:
            cards.append(card)
            continue

        try:
            store = load_plot_data_store(config.slug)
            card["density"] = store.prs_density_data(req.individual_id)
            card["available_for_individual"] = True
            card["unavailable_reason"] = None
        except Exception as e:
            logging.warning(
                "Failed to build risk overview for disease=%s individual=%s: %s",
                config.slug,
                req.individual_id,
                e,
            )
            card["unavailable_reason"] = str(e)
        cards.append(card)

    return {
        "individual_id": req.individual_id,
        "cohort": cohort.public_dict(),
        "diseases": cards,
    }
