from fastapi import APIRouter, Query

from runtime_agents import get_rag_agent, get_s2_agent
from schemas import SemanticScholarHealthResponse

router = APIRouter()


@router.get("/healthz")
def healthcheck():
    return {"status": "ok"}


@router.get("/api/health/rag")
def rag_health():
    return {"status": "ok", "reranker": get_rag_agent().reranker_status()}


@router.get("/api/health/semanticscholar", response_model=SemanticScholarHealthResponse)
def semanticscholar_health(probe: bool = Query(True)):
    s2_agent = get_s2_agent()
    if probe:
        return s2_agent.probe_health()
    status = s2_agent.get_health_status()
    status.setdefault("status", "unknown")
    status.setdefault("query", None)
    return status
