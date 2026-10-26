from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from cohort_registry import get_cohort_config
from disease_registry import list_diseases
from plot_data import load_plot_data_store
from kpredict_access import has_kpredict_access, kpredict_root
from kpredict_data import available_diseases, disease_overview, panel_finding_counts_by_disease
from schemas import DiseaseRiskOverviewRequest

router = APIRouter()


@router.get("/api/diseases")
def get_diseases():
    return {"diseases": [config.public_dict() for config in list_diseases()]}


@router.post("/api/disease-risk-overview")
def disease_risk_overview(req: DiseaseRiskOverviewRequest, request: Request):
    try:
        cohort = get_cohort_config(req.cohort)
    except ValueError:
        cohort = None

    if cohort is not None and cohort.slug == "kpredict":
        root = kpredict_root()
        if root is not None and has_kpredict_access(request):
            available = available_diseases(root)
            overview = disease_overview(root, req.individual_id)
            panel_findings = panel_finding_counts_by_disease(root, req.individual_id)
            cards = []
            for config in list_diseases():
                density = overview.get(config.slug)
                configured = config.slug in available
                cards.append({
                    **config.public_dict(),
                    "enabled": configured,
                    "available_for_individual": density is not None,
                    "density": density,
                    "panel_findings": panel_findings.get(config.slug, {
                        "finding_count": 0,
                        "alert_count": 0,
                        "carrier_count": 0,
                    }),
                    "unavailable_reason": None if density is not None else (
                        "This disease model is not applicable to the selected individual."
                        if configured else "No K-PREDICT data are available for this disease."
                    ),
                })
            cohort_payload = cohort.public_dict()
            cohort_payload["data_available"] = True
            cohort_payload["unavailable_reason"] = None
            return {"individual_id": req.individual_id, "cohort": cohort_payload, "diseases": cards}

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
        # The public 1000 Genomes release currently contains only the breast
        # cancer XPRS model. Do not render registry placeholders for diseases
        # that exist solely in the private multi-disease deployment.
        if not config.enabled:
            continue
        card = {
            **config.public_dict(),
            "available_for_individual": False,
            "density": None,
        }
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
