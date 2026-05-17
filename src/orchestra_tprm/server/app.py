"""FastAPI server for Orchestra TPRM — full graph execution + SSE streaming.

Endpoints
---------
GET  /health           — liveness probe
POST /run              — launch TPRM graph; returns run_id immediately
GET  /events/{run_id}  — SSE stream: node_done / verdict / error / done events
GET  /runs             — list active runs
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

_logger = logging.getLogger(__name__)

app = FastAPI(
    title="Orchestra TPRM",
    description="Multi-agent TPRM pipeline powered by Orchestra + Gemini.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registry: run_id → (queue, task, metadata)
_runs: dict[str, dict[str, Any]] = {}

# Friendly display names for pipeline nodes
_NODE_LABELS: dict[str, str] = {
    "bootstrap_node": "Bootstrap",
    "intake_node": "Document Intake",
    "vdr_gate": "VDR Completeness Gate",
    "router": "Document Router",
    "LegalAgent": "Legal Specialist",
    "SecurityAgent": "Security Specialist",
    "ExternalAgent": "External Intelligence",
    "CodeAgent": "Code Scanner",
    "FinancialAgent": "Financial Analyst",
    "SaaSMetricsAgent": "SaaS Metrics",
    "policy": "Policy Engine",
    "coordinator": "Report Coordinator",
    "pmi_planner": "PMI Planner",
}

# Vendor-mode node order (for progress display)
_VENDOR_PIPELINE = [
    "bootstrap_node", "intake_node", "router",
    "LegalAgent", "SecurityAgent", "ExternalAgent", "CodeAgent",
    "policy", "coordinator",
]
_MA_PIPELINE = [
    "bootstrap_node", "intake_node", "vdr_gate", "router",
    "LegalAgent", "SecurityAgent", "ExternalAgent", "CodeAgent",
    "FinancialAgent", "SaaSMetricsAgent",
    "policy", "coordinator", "pmi_planner",
]


def _sse(event_type: str, data: dict[str, Any]) -> str:
    return f"data: {json.dumps({'type': event_type, **data}, default=str)}\n\n"


_DRIVE_FOLDER_RE = re.compile(r"/folders/([a-zA-Z0-9_-]+)")


def _parse_drive_folder_id(url_or_id: str) -> str:
    """Extract folder ID from a Drive URL, or return the value as-is if already an ID."""
    m = _DRIVE_FOLDER_RE.search(url_or_id)
    return m.group(1) if m else url_or_id.strip()


def _build_provider(env: dict[str, str]) -> Any:
    if env.get("GOOGLE_API_KEY"):
        from orchestra.providers.google import GoogleProvider
        return GoogleProvider(api_key=env["GOOGLE_API_KEY"])
    from orchestra.providers.gemini_cli import GeminiCliProvider
    return GeminiCliProvider()


def _build_adapters(env: dict[str, str], mode_name: str) -> tuple[Any, str, str, str]:
    """Build adapters. Returns (Adapters, sheet_id, doc_id, drive_folder_id)."""
    from orchestra_tprm.adapters.gemini_files import GeminiFilesAdapter
    from orchestra_tprm.graph import Adapters

    use_real = bool(
        env.get("GOOGLE_API_KEY")
        and env.get("GOOGLE_CLOUD_PROJECT")
    )

    if use_real:
        from orchestra_tprm.adapters.bigquery import BigQueryAdapter
        from orchestra_tprm.adapters.docs import DocsAdapter
        from orchestra_tprm.adapters.drive import DriveAdapter
        from orchestra_tprm.adapters.github import GitHubAdapter
        from orchestra_tprm.adapters.sheets import SheetsAdapter
        adapters = Adapters(
            drive=DriveAdapter(),
            files=GeminiFilesAdapter(),
            sheets=SheetsAdapter(),
            docs=DocsAdapter(),
            bq=BigQueryAdapter(project=env.get("GOOGLE_CLOUD_PROJECT")),
            github=GitHubAdapter(token=env.get("GITHUB_TOKEN", "")),
        )
        sheet_id = env.get("SHEETS_VENDOR_TEMPLATE_ID", "")
        doc_id = env.get("DOCS_MA_TEMPLATE_ID", "")
        drive_folder_id = (
            env.get("DRIVE_VENDOR_FOLDER_ID", "")
            if mode_name == "vendor"
            else env.get("DRIVE_MA_FOLDER_ID", "")
        )
    else:
        from orchestra_tprm.adapters.bigquery import FakeBigQueryAdapter
        from orchestra_tprm.adapters.docs import FakeDocsAdapter
        from orchestra_tprm.adapters.drive import FakeDriveAdapter
        from orchestra_tprm.adapters.github import FakeGitHubAdapter
        from orchestra_tprm.adapters.sheets import FakeSheetsAdapter
        adapters = Adapters(
            drive=FakeDriveAdapter(),
            files=GeminiFilesAdapter(),
            sheets=FakeSheetsAdapter(),
            docs=FakeDocsAdapter(),
            bq=FakeBigQueryAdapter(),
            github=FakeGitHubAdapter(),
        )
        sheet_id = env.get("SHEETS_VENDOR_TEMPLATE_ID", "VENDOR-LOCAL")
        doc_id = env.get("DOCS_MA_TEMPLATE_ID", "")
        drive_folder_id = ""

    return adapters, sheet_id, doc_id, drive_folder_id


async def _execute_graph_task(
    run_id: str,
    queue: asyncio.Queue[str | None],
    mode: str,
    subject_name: str,
    packet_path: str,
    drive_folder_url: str | None = None,
    ma_scope: dict | None = None,
) -> None:
    """Background task: runs the TPRM graph and emits SSE events."""
    try:
        from orchestra.core.compiled import CompiledGraph
        from orchestra.core.context import ExecutionContext
        from orchestra.core.graph import WorkflowGraph
        from orchestra_tprm.graph import build_graph
        from orchestra_tprm.modes.config import load_mode

        env = dict(os.environ)

        await queue.put(_sse("started", {
            "run_id": run_id,
            "mode": mode,
            "subject_name": subject_name,
            "pipeline": _MA_PIPELINE if mode == "ma" else _VENDOR_PIPELINE,
        }))

        _runs[run_id]["status"] = "running"

        cfg = load_mode(mode)
        provider = _build_provider(env)
        adapters, sheet_id, doc_id, drive_folder_id = _build_adapters(env, mode)
        if drive_folder_url:
            drive_folder_id = _parse_drive_folder_id(drive_folder_url)

        # Read optional github_url from links.txt
        github_url = ""
        links_path = Path(packet_path) / "links.txt"
        if links_path.exists():
            for line in links_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped:
                    github_url = stripped
                    break

        graph = build_graph(
            cfg,
            adapters=adapters,
            drive_folder_id=drive_folder_id,
            sheet_id=sheet_id,
            doc_id=doc_id,
            bq_dataset=env.get("BQ_DATASET", "tprm_audit"),
            bq_table=env.get("BQ_TABLE", "tprm_findings"),
            github_url=github_url,
        )

        compiled = (
            graph if isinstance(graph, CompiledGraph)
            else graph.compile()  # type: ignore[union-attr]
        )

        context = ExecutionContext(run_id=run_id, provider=provider)
        initial: dict[str, Any] = {
            "mode": cfg.name,
            "subject_name": subject_name,
            "packet_path": packet_path,
            "ma_scope": ma_scope,
        }

        # Launch graph in a sub-task so we can poll progress concurrently.
        graph_task: asyncio.Task[dict[str, Any]] = asyncio.create_task(
            compiled.run(
                initial_state=None,
                input=initial,
                context=context,
                provider=provider,
                persist=False,
            )
        )

        seen_nodes: set[str] = set()
        while not graph_task.done():
            await asyncio.sleep(2)
            for node in list(context.node_execution_order):
                if node not in seen_nodes:
                    seen_nodes.add(node)
                    label = _NODE_LABELS.get(node, node)
                    await queue.put(_sse("node_done", {"node": node, "label": label}))

        final_state = await graph_task

        # Flush any nodes that completed in the final poll window.
        for node in list(context.node_execution_order):
            if node not in seen_nodes:
                seen_nodes.add(node)
                label = _NODE_LABELS.get(node, node)
                await queue.put(_sse("node_done", {"node": node, "label": label}))

        findings_raw = final_state.get("findings", [])
        findings = [
            f if isinstance(f, dict) else f.model_dump()
            for f in findings_raw
        ]
        verdict = final_state.get("policy_verdict", "")
        risk_score = final_state.get("risk_score", 0)

        _runs[run_id]["status"] = "done"
        _runs[run_id]["verdict"] = verdict
        _runs[run_id]["risk_score"] = risk_score
        _runs[run_id]["findings_count"] = len(findings)

        await queue.put(_sse("verdict", {
            "policy_verdict": verdict,
            "risk_score": risk_score,
            "findings_count": len(findings),
            "findings": findings,
            "verdict_doc_id": final_state.get("verdict_doc_id", ""),
            "verdict_local_path": final_state.get("verdict_local_path", ""),
            "ic_memo": final_state.get("ic_memo"),
            "pmi_plan": final_state.get("pmi_plan"),
        }))

    except Exception as exc:
        _logger.exception("Graph execution failed run_id=%s", run_id)
        _runs[run_id]["status"] = "error"
        await queue.put(_sse("error", {"message": str(exc)}))
    finally:
        await queue.put(_sse("done", {"run_id": run_id}))
        await queue.put(None)  # sentinel — closes SSE stream


# ── Request / Response models ─────────────────────────────────────────────────


class RunRequest(BaseModel):
    mode: Literal["vendor", "ma"]
    subject_name: str
    packet_path: str
    drive_folder_url: str | None = None
    ma_scope: dict | None = None  # serialised MAScope; parsed downstream


class RunResponse(BaseModel):
    run_id: str
    status: str = "accepted"


class HealthResponse(BaseModel):
    status: str = "ok"


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/run", response_model=RunResponse, status_code=200, tags=["tprm"])
async def run_tprm(request: RunRequest) -> RunResponse:
    """Launch a TPRM graph run. Returns run_id immediately; stream events via /events/{run_id}."""

    run_id = uuid.uuid4().hex
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    task = asyncio.create_task(
        _execute_graph_task(
            run_id, queue, request.mode, request.subject_name,
            request.packet_path, request.drive_folder_url,
            request.ma_scope,
        )
    )
    _runs[run_id] = {
        "queue": queue,
        "task": task,
        "mode": request.mode,
        "subject_name": request.subject_name,
        "status": "accepted",
        "created_at": time.time(),
    }
    return RunResponse(run_id=run_id, status="accepted")


@app.get("/events/{run_id}", tags=["tprm"])
async def events(run_id: str) -> StreamingResponse:
    """Server-Sent Events stream for a TPRM run."""
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

    queue: asyncio.Queue[str | None] = _runs[run_id]["queue"]

    async def _stream() -> Any:
        deadline = time.monotonic() + 900  # 15-minute hard cap
        while True:
            if time.monotonic() > deadline:
                yield _sse("error", {"message": "Run exceeded 15-minute limit"})
                break
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=30)
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
                continue
            if msg is None:
                break
            yield msg

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/runs", tags=["tprm"])
async def list_runs() -> dict[str, Any]:
    """List active and recent runs (excludes queue/task objects)."""
    summary = {
        run_id: {
            k: v for k, v in meta.items()
            if k not in ("queue", "task")
        }
        for run_id, meta in _runs.items()
    }
    return {"runs": summary}


# ── Static files (production: React build copied to /app/static) ──────────────

_STATIC_DIR = Path(os.environ.get("STATIC_DIR", Path(__file__).parent.parent.parent.parent / "static"))

if _STATIC_DIR.is_dir():
    _assets = _STATIC_DIR / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str) -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")
