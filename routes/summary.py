from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

import config
from disease_registry import enabled_disease_config
from runtime_agents import get_expl_agent
from schemas import (
    SummaryPreviewResponse,
    SummaryRequest,
    SummaryResponse,
    TaskStartResponse,
)
from session_logs import load_session_log, maybe_save_session_log
from task_manager import create_task, fail_task, finish_task, push_task_event

router = APIRouter()


def _validate_generation_model(model: str | None) -> None:
    if model and model not in config.GENERATION_MODEL_IDS:
        raise HTTPException(status_code=400, detail=f"Unsupported generation model: {model}")


def run_summary_request(req: SummaryRequest, progress_callback=None) -> dict[str, Any]:
    disease_config = enabled_disease_config(req.disease)
    expl_agent = get_expl_agent(req.model)
    result = expl_agent.build_explanation(
        pid=req.individual_id,
        evaluate=False,
        gene_count=req.gene_count,
        language=req.language or "en",
        progress_callback=progress_callback,
    )

    session_id = str(uuid.uuid4())
    session = load_session_log(req.individual_id, session_id)
    session["disease"] = disease_config.slug
    session["disease_display_name"] = disease_config.display_name
    session["gene_count"] = req.gene_count
    session["sig_threshold"] = None
    session["generation_model"] = req.model or config.DEFAULT_GENERATION_MODEL
    session["conversation_state"]["active_genes"] = result.get("Discussed Genes", [])
    session["references"] = result.get("References", [])
    session["language"] = req.language or "en"
    session["source_path"] = result.get("Source Path")
    session["gene_count_used"] = result.get("Gene Count Used")
    session["threshold_used"] = None
    session["simple_summary"] = result.get("Simple Explanation", "")
    session["detailed_summary"] = result.get("Detailed Explanation", result.get("Generated Explanation", ""))
    session["report_payload"] = result.get("Report Payload", {})
    session["timings"] = result.get("Timings", {})
    session["messages"].append({
        "role": "assistant",
        "type": "summary",
        "timestamp": datetime.now().isoformat(),
        "content": result.get("Simple Explanation", ""),
    })
    maybe_save_session_log(req.individual_id, session_id, session)
    return {
        "summary": result.get("Simple Explanation", ""),
        "simple_summary": result.get("Simple Explanation", ""),
        "detailed_summary": result.get("Detailed Explanation", result.get("Generated Explanation", "")),
        "references": result.get("References", []),
        "session_id": session_id,
        "report_ready": True,
    }


@router.post("/api/summary", response_model=SummaryResponse)
def summary(req: SummaryRequest):
    _validate_generation_model(req.model)
    try:
        return run_summary_request(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error("Failed to write summary session log: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/summary_preview", response_model=SummaryPreviewResponse)
def summary_preview(req: SummaryRequest):
    try:
        enabled_disease_config(req.disease)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    expl_agent = get_expl_agent()
    top, _ = expl_agent.gene_agent.get_top_genes(
        pid=req.individual_id,
        top_n=req.gene_count,
    )
    genes = list(top["Gene"].values)[: req.gene_count]
    return {"genes": genes, "gene_count": len(genes)}


@router.post("/api/summary/start", response_model=TaskStartResponse)
def start_summary_task(req: SummaryRequest):
    _validate_generation_model(req.model)
    try:
        enabled_disease_config(req.disease)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    task_id = create_task("summary")

    def worker():
        try:
            result = run_summary_request(req, progress_callback=lambda msg: push_task_event(task_id, "progress", {"message": msg}))
            finish_task(task_id, result)
        except Exception as e:
            logging.exception("Summary task failed")
            fail_task(task_id, str(e))

    threading.Thread(target=worker, daemon=True).start()
    return {"task_id": task_id}
