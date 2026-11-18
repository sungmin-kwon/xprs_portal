from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query, Request, Response

from kpredict_access import ACCESS_COOKIE, require_kpredict_access
from kpredict_data import (
    cohort_analysis,
    cross_disease_gene_heatmap,
    rare_findings,
    rare_findings_overview,
    panel_gene_options,
    risk_filtered_individuals,
    trait_overview,
)


router = APIRouter()


@router.get("/api/kpredict/cohort-analysis", include_in_schema=False)
def get_cohort_analysis(request: Request, disease: str):
    root = require_kpredict_access(request)
    try:
        return cohort_analysis(root, disease)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/api/kpredict/panel-genes", include_in_schema=False)
def get_panel_genes(request: Request, disease: str):
    root = require_kpredict_access(request)
    try:
        return {"disease": disease, "genes": panel_gene_options(root, disease)}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/api/kpredict/access", include_in_schema=False)
def establish_kpredict_access(request: Request, response: Response) -> None:
    require_kpredict_access(request)
    response.headers["Cache-Control"] = "no-store"
    supplied = (
        request.headers.get("X-XPRS-KPREDICT-Token")
        or request.headers.get("X-XPRS-Admin-Token")
    )
    if supplied:
        response.set_cookie(
            ACCESS_COOKIE,
            supplied,
            max_age=12 * 60 * 60,
            httponly=True,
            samesite="strict",
            secure=os.getenv("XPRS_COOKIE_SECURE", "false").lower() in {"1", "true", "yes", "on"},
        )


@router.get("/api/kpredict/rare-findings", include_in_schema=False)
def get_rare_findings(request: Request, individual_id: str, disease: str):
    root = require_kpredict_access(request)
    response = rare_findings(root, individual_id, disease)
    return response


@router.get("/api/kpredict/rare-findings-overview", include_in_schema=False)
def get_rare_findings_overview(request: Request, individual_id: str):
    root = require_kpredict_access(request)
    return rare_findings_overview(root, individual_id)


@router.get("/api/kpredict/trait-overview", include_in_schema=False)
def get_trait_overview(request: Request, individual_id: str = Query(min_length=1, max_length=64)):
    root = require_kpredict_access(request)
    try:
        return trait_overview(root, individual_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/api/kpredict/cross-disease-gene-heatmap", include_in_schema=False)
def get_cross_disease_gene_heatmap(
    request: Request,
    individual_id: str,
    top_fraction: float = Query(default=0.0025, ge=0.0005, le=0.05),
    min_diseases: int = Query(default=3, ge=2, le=6),
    max_genes: int = Query(default=20, ge=8, le=30),
):
    root = require_kpredict_access(request)
    try:
        return cross_disease_gene_heatmap(
            root,
            individual_id,
            top_fraction=top_fraction,
            min_diseases=min_diseases,
            max_genes=max_genes,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/api/kpredict/individual-risk-filter", include_in_schema=False)
def get_individual_risk_filter(
    request: Request,
    disease: str,
    percentile_min: float = Query(default=0.0, ge=0.0, le=100.0),
    percentile_max: float = Query(default=100.0, ge=0.0, le=100.0),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=5000, ge=1, le=5000),
    rare_status: str = Query(default="all", pattern="^(all|alert|carrier|finding|none)$"),
    gene: str = Query(default="", max_length=120),
):
    root = require_kpredict_access(request)
    try:
        return risk_filtered_individuals(
            root,
            disease,
            percentile_min=percentile_min,
            percentile_max=percentile_max,
            order=order,
            limit=limit,
            rare_status=rare_status,
            gene=gene,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
