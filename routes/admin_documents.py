from __future__ import annotations

import hmac
import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from config import STATIC_DIR
from runtime_agents import get_rag_agent

router = APIRouter()


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


@router.get("/api/admin/documents", include_in_schema=False)
def documents_for_gene(
    request: Request,
    response: Response,
    gene: str = Query(min_length=1, max_length=64),
    pool: Literal["all", "general", "phenotype", "opentargets", "other"] = "all",
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
        phenotype=phenotype.strip(),
        search=search,
        sort=sort,
        offset=offset,
        limit=limit,
    )
