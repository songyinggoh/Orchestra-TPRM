"""FastAPI application skeleton for Orchestra TPRM.

Endpoints
---------
GET  /health           — liveness probe
POST /run              — accept a new TPRM run (stub; graph execution deferred)
GET  /events/{run_id}  — SSE stream for run events (stub; real streaming deferred)
"""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI(
    title="Orchestra TPRM",
    description="Multi-agent TPRM pipeline powered by Orchestra + Gemini.",
    version="0.1.0",
)


# ── Request / Response models ─────────────────────────────────────────────────

class RunRequest(BaseModel):
    mode: Literal["vendor", "ma"]
    subject_name: str
    packet_path: str


class RunResponse(BaseModel):
    run_id: str
    status: str = "accepted"


class HealthResponse(BaseModel):
    status: str = "ok"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    """Liveness probe — always returns 200 {"status": "ok"}."""
    return HealthResponse(status="ok")


@app.post("/run", response_model=RunResponse, status_code=200, tags=["tprm"])
async def run_tprm(request: RunRequest) -> RunResponse:
    """Accept a new TPRM run request.

    Currently a stub — returns an accepted run_id without launching the graph.
    Full graph execution will be wired in a subsequent task.
    """
    run_id = str(uuid.uuid4())
    # TODO (Task 12.F+): launch background graph execution, persist run state.
    return RunResponse(run_id=run_id, status="accepted")


@app.get("/events/{run_id}", tags=["tprm"])
async def events(run_id: str) -> StreamingResponse:
    """Server-Sent Events stream for a TPRM run.

    Currently a stub — immediately closes the stream with a single
    ``data: {"status": "pending"}`` message.
    Real streaming (Pub/Sub → SSE forwarding) is deferred to a later task.
    """

    async def _stub_generator():  # type: ignore[return]
        yield f'data: {{"run_id": "{run_id}", "status": "pending"}}\n\n'
        # Stream ends; real implementation will subscribe to the event bus here.

    return StreamingResponse(
        _stub_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
