from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

import config
from disease_registry import enabled_disease_config
from runtime_agents import get_expl_agent
from schemas import ChatRequest, ChatResponse, TaskStartResponse
from session_logs import load_session_log, maybe_save_session_log
from task_manager import create_task, fail_task, finish_task, push_task_event

router = APIRouter()


def _validate_generation_model(model: str | None) -> None:
    if model and model not in config.GENERATION_MODEL_IDS:
        raise HTTPException(status_code=400, detail=f"Unsupported generation model: {model}")


def run_chat_request(req: ChatRequest, progress_callback=None) -> ChatResponse:
    disease_config = enabled_disease_config(req.disease)
    expl_agent = get_expl_agent(req.model)
    answer_id = str(uuid.uuid4())
    session_id = req.session_id or str(uuid.uuid4())
    session = load_session_log(req.individual_id, session_id)
    session["disease"] = disease_config.slug
    session["disease_display_name"] = disease_config.display_name
    try:
        gene_count = int(session.get("gene_count") or session.get("gene_count_used") or 2)
    except (TypeError, ValueError):
        gene_count = 2
    gene_count = max(1, min(gene_count, expl_agent.MAX_SUMMARY_GENES))
    existing_references = session.get("references", [])
    recent_history = [
        str(msg.get("content") or "")
        for msg in session.get("messages", [])[-4:]
        if isinstance(msg, dict) and (msg.get("content") or "")
    ]
    followup_result = expl_agent.answer_followup(
        req.individual_id,
        req.query,
        gene_count=gene_count,
        existing_references=existing_references,
        conversation_history=recent_history,
        conversation_state=session.get("conversation_state", {}),
        language=req.language or session.get("language", "en"),
        progress_callback=progress_callback,
    )
    answer_text = followup_result["Generated Answer"]
    references = followup_result.get("References", [])
    store_in_history = bool(followup_result.get("Store In History", True))

    if store_in_history:
        session["messages"].append({
            "role": "user",
            "type": "followup",
            "timestamp": datetime.now().isoformat(),
            "content": req.query,
        })

        session["messages"].append({
            "role": "assistant",
            "type": "followup_answer",
            "timestamp": datetime.now().isoformat(),
            "answer_id": answer_id,
            "content": answer_text,
        })
    session["conversation_state"] = followup_result.get("Conversation State", session.get("conversation_state", {}))
    session["references"] = references
    session["language"] = req.language or session.get("language", "en")

    maybe_save_session_log(req.individual_id, session_id, session)
    return ChatResponse(
        answer=answer_text,
        answer_id=answer_id,
        session_id=session_id,
        references=references,
    )


@router.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    _validate_generation_model(req.model)
    try:
        return run_chat_request(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error("Failed to write chat session log: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/chat/start", response_model=TaskStartResponse)
def start_chat_task(req: ChatRequest):
    _validate_generation_model(req.model)
    try:
        enabled_disease_config(req.disease)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    task_id = create_task("chat")

    def worker():
        try:
            result = run_chat_request(req, progress_callback=lambda msg: push_task_event(task_id, "progress", {"message": msg}))
            finish_task(task_id, result.model_dump())
        except Exception as e:
            logging.exception("Chat task failed")
            fail_task(task_id, str(e))

    threading.Thread(target=worker, daemon=True).start()
    return {"task_id": task_id}
