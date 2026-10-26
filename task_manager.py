from __future__ import annotations

import threading
import uuid
from datetime import datetime
from queue import Queue
from typing import Any

_TASKS: dict[str, dict[str, Any]] = {}
_REQUEST_TASKS: dict[tuple[str, str, str], str] = {}
_LOCK = threading.Lock()


def create_task_once(
    task_type: str,
    cohort: str = "1000_genomes",
    request_id: str | None = None,
) -> tuple[str, bool]:
    """Create a task, or return the task already created for a retried request."""
    normalized_request_id = (request_id or "").strip()[:128]
    request_key = (
        task_type,
        cohort,
        normalized_request_id,
    ) if normalized_request_id else None

    with _LOCK:
        if request_key:
            existing_id = _REQUEST_TASKS.get(request_key)
            if existing_id in _TASKS:
                return existing_id, False

        task_id = str(uuid.uuid4())
        _TASKS[task_id] = {
            "type": task_type,
            "cohort": cohort,
            "request_id": normalized_request_id or None,
            "queue": Queue(),
            "done": False,
            "result": None,
            "error": None,
            "created_at": datetime.now().isoformat(),
        }
        if request_key:
            _REQUEST_TASKS[request_key] = task_id
    return task_id, True


def create_task(task_type: str, cohort: str = "1000_genomes") -> str:
    task_id, _ = create_task_once(task_type, cohort)
    return task_id


def get_task(task_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _TASKS.get(task_id)


def push_task_event(task_id: str, event_type: str, payload: dict[str, Any]) -> None:
    task = get_task(task_id)
    if not task:
        return
    task["queue"].put({"event": event_type, "data": payload})


def finish_task(task_id: str, result: dict[str, Any]) -> None:
    with _LOCK:
        task = _TASKS.get(task_id)
        if not task:
            return
        task["done"] = True
        task["result"] = result
    push_task_event(task_id, "complete", result)


def fail_task(task_id: str, message: str) -> None:
    with _LOCK:
        task = _TASKS.get(task_id)
        if not task:
            return
        task["done"] = True
        task["error"] = message
    push_task_event(task_id, "failed", {"message": message})
