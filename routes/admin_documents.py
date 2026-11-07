from __future__ import annotations

import hmac
import os
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import EUROPE_PMC_CACHE_DIR, S2_CACHE_DIR, STATIC_DIR
from retrieval_coverage import build_retrieval_coverage
from runtime_agents import get_rag_agent, get_retrieval_admin_status, get_runtime_agents

router = APIRouter()


class ManualRetrievalRequest(BaseModel):
    gene: str = Field(min_length=1, max_length=64)
    pool: Literal["general", "phenotype"] = "general"
    phenotype: str | None = Field(default=None, max_length=100)


class DocumentDeletionRequest(BaseModel):
    document_id: str = Field(min_length=1, max_length=512)


def _require_admin_access(request: Request) -> None:
    """Protect the unlinked browser with XPRS_ADMIN_TOKEN.

    When a token is configured, return 404 instead of advertising that an
    administrative route exists. An unset token disables the route so a
    forgotten production setting cannot expose stored literature.
    """
    expected = os.getenv("XPRS_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=404, detail="Not found")
    supplied = (
        request.headers.get("X-XPRS-Admin-Token")
        or request.cookies.get("xprs_admin_access")
        or ""
    )
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/admin/documents", include_in_schema=False)
def admin_documents_page():
    if not os.getenv("XPRS_ADMIN_TOKEN", "").strip():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        STATIC_DIR / "admin-documents.html",
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"},
    )


@router.post("/api/admin/access", include_in_schema=False)
def establish_admin_access(request: Request, response: Response) -> None:
    _require_admin_access(request)
    response.headers["Cache-Control"] = "no-store"
    if request.headers.get("X-XPRS-Admin-Token"):
        response.set_cookie(
            "xprs_admin_access",
            request.headers["X-XPRS-Admin-Token"],
            max_age=8 * 60 * 60,
            httponly=True,
            samesite="strict",
            secure=os.getenv("XPRS_COOKIE_SECURE", "false").lower() in {"1", "true", "yes", "on"},
        )


@router.get("/api/admin/document-inventory", include_in_schema=False)
def document_inventory(request: Request, response: Response):
    _require_admin_access(request)
    response.headers["Cache-Control"] = "no-store"
    return get_rag_agent().document_inventory()


@router.get("/api/admin/retrieval-coverage", include_in_schema=False)
def retrieval_coverage(request: Request, response: Response):
    _require_admin_access(request)
    response.headers["Cache-Control"] = "no-store"
    rag = get_rag_agent()
    runtime = get_retrieval_admin_status()
    return build_retrieval_coverage(
        inventory=rag.document_inventory(),
        cache_dirs={
            "semanticscholar": S2_CACHE_DIR,
            "europe_pmc": EUROPE_PMC_CACHE_DIR,
        },
        semantic_scholar=runtime["semantic_scholar"],
        provider_attempts=runtime["provider_attempts"],
        queue_status=runtime["queue"],
        runtime_status=runtime["runtime_cooldowns"],
    )


@router.post("/api/admin/retrieval-query", include_in_schema=False)
def manual_retrieval_query(
    payload: ManualRetrievalRequest,
    request: Request,
    response: Response,
):
    _require_admin_access(request)
    response.headers["Cache-Control"] = "no-store"
    gene = payload.gene.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,63}", gene):
        raise HTTPException(status_code=422, detail="Invalid gene symbol")
    phenotype = (payload.phenotype or "").strip().lower() or None
    if payload.pool == "phenotype" and not phenotype:
        raise HTTPException(status_code=422, detail="A phenotype is required")
    if payload.pool == "general":
        phenotype = None

    progress: list[str] = []
    evidence = get_runtime_agents()["evidence_agent"]
    result = evidence.manually_index_pool(
        gene,
        phenotype=phenotype,
        progress_callback=progress.append,
    )
    return {"gene": gene, "phenotype": phenotype, "progress": progress, **result}


@router.post("/api/admin/semanticscholar-check", include_in_schema=False)
def semantic_scholar_key_check(request: Request, response: Response):
    _require_admin_access(request)
    response.headers["Cache-Control"] = "no-store"
    return get_runtime_agents()["evidence_agent"].manually_probe_semantic_scholar()


@router.get("/api/admin/documents", include_in_schema=False)
def documents_for_gene(
    request: Request,
    response: Response,
    gene: str = Query(min_length=1, max_length=64),
    pool: Literal["all", "general", "phenotype", "opentargets", "other"] = "all",
    source: Literal["all", "europe_pmc", "semanticscholar"] = "all",
    phenotype: str = Query("", max_length=100),
    search: str = Query("", max_length=200),
    sort: Literal["citations_desc", "title", "pool"] = "citations_desc",
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    _require_admin_access(request)
    response.headers["Cache-Control"] = "no-store"
    return get_rag_agent().browse_documents(
        gene=gene.strip(),
        pool=pool,
        source=source,
        phenotype=phenotype.strip(),
        search=search,
        sort=sort,
        offset=offset,
        limit=limit,
    )


@router.post("/api/admin/document-delete", include_in_schema=False)
def delete_indexed_document(
    payload: DocumentDeletionRequest,
    request: Request,
    response: Response,
):
    """Delete one exact vector-store record; provider caches remain intact."""
    _require_admin_access(request)
    response.headers["Cache-Control"] = "no-store"
    deleted = get_rag_agent().delete_document_by_id(payload.document_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Indexed document not found")
    return {"deleted": True, "cache_preserved": True, "document": deleted}
