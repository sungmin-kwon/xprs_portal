from __future__ import annotations

import json
import logging
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

from fastapi import HTTPException

from config import EPHEMERAL_SESSION_LIMIT, LOG_DIR, SESSION_LOGGING_ENABLED


_MEMORY_SESSIONS: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
_MEMORY_SESSIONS_LOCK = RLock()


def _memory_session_key(individual_id: str, session_id: str) -> tuple[str, str]:
    return individual_id, session_id


def _load_memory_session(individual_id: str, session_id: str) -> dict[str, Any] | None:
    key = _memory_session_key(individual_id, session_id)
    with _MEMORY_SESSIONS_LOCK:
        payload = _MEMORY_SESSIONS.get(key)
        if payload is None:
            return None
        _MEMORY_SESSIONS.move_to_end(key)
        return deepcopy(payload)


def _load_memory_session_by_id(
    session_id: str,
    individual_id: str | None = None,
) -> dict[str, Any] | None:
    with _MEMORY_SESSIONS_LOCK:
        if individual_id is not None:
            key = _memory_session_key(individual_id, session_id)
            payload = _MEMORY_SESSIONS.get(key)
            if payload is None:
                return None
            _MEMORY_SESSIONS.move_to_end(key)
            return deepcopy(payload)

        for key in reversed(_MEMORY_SESSIONS):
            if key[1] == session_id:
                _MEMORY_SESSIONS.move_to_end(key)
                return deepcopy(_MEMORY_SESSIONS[key])
    return None


def _save_memory_session(individual_id: str, session_id: str, payload: dict) -> None:
    key = _memory_session_key(individual_id, session_id)
    with _MEMORY_SESSIONS_LOCK:
        _MEMORY_SESSIONS[key] = deepcopy(payload)
        _MEMORY_SESSIONS.move_to_end(key)
        while len(_MEMORY_SESSIONS) > EPHEMERAL_SESSION_LIMIT:
            _MEMORY_SESSIONS.popitem(last=False)


def session_log_path(individual_id: str, session_id: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / f"session_{individual_id}_{session_id}.json"


def _normalize_legacy_payload(payload: dict) -> dict:
    if "individual_id" not in payload and "patient_id" in payload:
        payload["individual_id"] = payload.pop("patient_id")
    report = payload.get("report_payload")
    if isinstance(report, dict) and "individual_id" not in report and "patient_id" in report:
        report["individual_id"] = report.pop("patient_id")
    return payload


def load_session_log(individual_id: str, session_id: str) -> dict:
    memory_payload = _load_memory_session(individual_id, session_id)
    if memory_payload is not None:
        return _normalize_legacy_payload(memory_payload)

    path = session_log_path(individual_id, session_id)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = _normalize_legacy_payload(json.load(f))
                payload.setdefault("simple_summary", "")
                payload.setdefault("detailed_summary", "")
                payload.setdefault("report_payload", {})
                payload.setdefault("references", [])
                payload.setdefault("timings", {})
                payload.setdefault("language", "en")
                payload.setdefault("gene_count", None)
                payload.setdefault("messages", [])
                payload.setdefault("conversation_state", {
                    "active_genes": [],
                    "active_phenotypes": [],
                    "active_intent": None,
                    "last_user_query": None,
                    "last_resolved_question": None,
                })
                return payload
        except Exception as e:
            logging.error("Failed to read session log %s: %s", path, e)

    now_iso = datetime.now().isoformat()
    return {
        "session_id": session_id,
        "individual_id": individual_id,
        "created_at": now_iso,
        "updated_at": now_iso,
        "sig_threshold": None,
        "gene_count": 2,
        "conversation_state": {
            "active_genes": [],
            "active_phenotypes": [],
            "active_intent": None,
            "last_user_query": None,
            "last_resolved_question": None,
        },
        "simple_summary": "",
        "detailed_summary": "",
        "report_payload": {},
        "references": [],
        "timings": {},
        "language": "en",
        "messages": [],
    }


def find_session_log_path(session_id: str, individual_id: str | None = None) -> Path:
    if individual_id:
        path = session_log_path(individual_id, session_id)
        if path.exists():
            return path
        raise HTTPException(status_code=404, detail="Session log not found")

    matches = sorted(LOG_DIR.glob(f"session_*_{session_id}.json"))
    if not matches:
        raise HTTPException(status_code=404, detail="Session log not found")
    return matches[0]


def load_session_log_by_id(session_id: str, individual_id: str | None = None) -> dict[str, Any]:
    memory_payload = _load_memory_session_by_id(
        session_id,
        individual_id=individual_id,
    )
    if memory_payload is not None:
        payload = _normalize_legacy_payload(memory_payload)
        payload.setdefault("simple_summary", "")
        payload.setdefault("detailed_summary", "")
        payload.setdefault("report_payload", {})
        payload.setdefault("references", [])
        payload.setdefault("timings", {})
        payload.setdefault("language", "en")
        payload.setdefault("gene_count", None)
        payload.setdefault("messages", [])
        return payload

    path = find_session_log_path(session_id, individual_id=individual_id)
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = _normalize_legacy_payload(json.load(f))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read session log: {exc}") from exc

    payload.setdefault("simple_summary", "")
    payload.setdefault("detailed_summary", "")
    payload.setdefault("report_payload", {})
    payload.setdefault("references", [])
    payload.setdefault("timings", {})
    payload.setdefault("language", "en")
    payload.setdefault("gene_count", None)
    payload.setdefault("messages", [])
    return payload


def build_chat_markdown(session: dict[str, Any]) -> str:
    selection_line = (
        f"- Genes Included: {session.get('gene_count_used') or session.get('gene_count')}"
        if session.get("gene_count_used") or session.get("gene_count")
        else f"- Legacy Threshold Used: {session.get('threshold_used') if session.get('threshold_used') is not None else session.get('sig_threshold')}"
    )
    lines = [
        "# XPRS Session Chat Export",
        "",
        f"- Session ID: {session.get('session_id') or ''}",
        f"- Individual ID: {session.get('individual_id') or ''}",
        f"- Language: {session.get('language') or 'en'}",
        selection_line,
        f"- Created At: {session.get('created_at') or ''}",
        f"- Updated At: {session.get('updated_at') or ''}",
        "",
    ]

    messages = session.get("messages") or []
    if not messages and session.get("simple_summary"):
        messages = [{
            "role": "assistant",
            "type": "summary",
            "timestamp": session.get("created_at"),
            "content": session.get("simple_summary"),
        }]

    for msg in messages:
        role = (msg.get("role") or "assistant").capitalize()
        msg_type = msg.get("type") or "message"
        timestamp = msg.get("timestamp") or ""
        lines.extend([
            f"## {role} ({msg_type})",
            "",
            f"_Timestamp: {timestamp}_",
            "",
            str(msg.get("content") or "").rstrip(),
            "",
        ])

    if session.get("references"):
        lines.extend([
            "## References",
            "",
        ])
        for ref in session.get("references", []):
            title = ref.get("title") or "Untitled"
            gene = ref.get("gene") or ""
            url = ref.get("url") or ""
            lines.append(f"- [{ref.get('n', '')}] {title}" + (f" ({gene})" if gene else "") + (f" - {url}" if url else ""))
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def save_session_log(individual_id: str, session_id: str, payload: dict) -> None:
    payload["updated_at"] = datetime.now().isoformat()
    path = session_log_path(individual_id, session_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def maybe_save_session_log(
    individual_id: str,
    session_id: str,
    payload: dict,
    *,
    force_ephemeral: bool = False,
) -> None:
    if SESSION_LOGGING_ENABLED and not force_ephemeral:
        save_session_log(individual_id, session_id, payload)
        return
    payload["updated_at"] = datetime.now().isoformat()
    _save_memory_session(individual_id, session_id, payload)
