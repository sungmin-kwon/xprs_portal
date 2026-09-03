from __future__ import annotations

import threading
import uuid
from datetime import datetime
from queue import Queue
from typing import Any

_TASKS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def create_task(task_type: str) -> str:
    task_id = str(uuid.uuid4())
    with _LOCK:
        _TASKS[task_id] = {
            "type": task_type,
            "queue": Queue(),
            "done": False,
            "result": None,
            "error": None,
            "created_at": datetime.now().isoformat(),
        }
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
