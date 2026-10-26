from __future__ import annotations

import json
from queue import Empty

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from task_manager import get_task
from kpredict_access import require_kpredict_access

router = APIRouter()


def _authorize_task(task, request: Request) -> None:
    if task.get("cohort") == "kpredict":
        require_kpredict_access(request)


def _terminal_event(task) -> dict | None:
    if not task.get("done"):
        return None
    if task.get("error"):
        return {"event": "failed", "data": {"message": task["error"]}}
    return {"event": "complete", "data": task.get("result") or {}}


@router.get("/api/tasks/{task_id}")
def task_status(task_id: str, request: Request):
    """Return durable task state when a browser needs to recover its SSE stream."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    _authorize_task(task, request)
    terminal = _terminal_event(task)
    if terminal:
        return {
            "status": terminal["event"],
            "result": terminal["data"] if terminal["event"] == "complete" else None,
            "error": terminal["data"].get("message") if terminal["event"] == "failed" else None,
        }
    return {"status": "running", "result": None, "error": None}


@router.get("/api/tasks/{task_id}/events")
def stream_task_events(task_id: str, request: Request):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    _authorize_task(task, request)

    def event_stream():
        # A reconnect may arrive after the original stream consumed the terminal
        # queue item. Replay the stored result instead of losing a completed task.
        terminal = _terminal_event(get_task(task_id) or task)
        if terminal:
            data = json.dumps(terminal["data"], ensure_ascii=False)
            yield f'event: {terminal["event"]}\ndata: {data}\n\n'
            return

        queue = task["queue"]
        while True:
            try:
                item = queue.get(timeout=15)
            except Empty:
                yield ": keep-alive\n\n"
                latest = get_task(task_id)
                if not latest or latest.get("done"):
                    terminal = _terminal_event(latest or {})
                    if terminal:
                        data = json.dumps(terminal["data"], ensure_ascii=False)
                        yield f'event: {terminal["event"]}\ndata: {data}\n\n'
                    break
                continue

            event = item.get("event", "message")
            data = json.dumps(item.get("data", {}), ensure_ascii=False)
            yield f"event: {event}\ndata: {data}\n\n"
            if event in {"complete", "failed"}:
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
