from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from session_logs import build_chat_markdown, load_session_log_by_id
from kpredict_access import require_kpredict_access

router = APIRouter()


@router.get("/api/session/{session_id}/chat.md")
def export_chat_markdown(session_id: str, request: Request):
    session = load_session_log_by_id(session_id)
    if session.get("cohort") == "kpredict":
        require_kpredict_access(request)
    content = build_chat_markdown(session)
    filename = f"xprs_chat_{session.get('individual_id') or 'session'}_{session_id}.md"
    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/session/{session_id}/chat.json")
def export_chat_json(session_id: str, request: Request):
    session = load_session_log_by_id(session_id)
    if session.get("cohort") == "kpredict":
        require_kpredict_access(request)
    filename = f"xprs_chat_{session.get('individual_id') or 'session'}_{session_id}.json"
    payload = json.dumps(session, ensure_ascii=False, indent=2).encode("utf-8")
    return StreamingResponse(
        iter([payload]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
