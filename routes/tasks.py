from __future__ import annotations

import json
from queue import Empty

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from task_manager import get_task

router = APIRouter()


@router.get("/api/tasks/{task_id}/events")
def stream_task_events(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    def event_stream():
        queue = task["queue"]
        while True:
            try:
                item = queue.get(timeout=15)
            except Empty:
                yield ": keep-alive\n\n"
                latest = get_task(task_id)
                if not latest or latest.get("done"):
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
