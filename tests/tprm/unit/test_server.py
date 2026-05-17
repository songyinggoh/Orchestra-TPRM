"""Unit tests for the FastAPI server — HTTP layer only.

Background graph execution is mocked so tests run instantly without
spawning Gemini CLI subprocesses.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from orchestra_tprm.server.app import app

client = TestClient(app)


# ── Mock helpers ──────────────────────────────────────────────────────────────


async def _noop_graph_task(run_id, queue, mode, subject_name, packet_path, drive_folder_url=None, ma_scope=None):
    """Instant stub: emits started + done then closes the stream."""
    import json
    queue.put_nowait(f'data: {json.dumps({"type": "started", "run_id": run_id})}\n\n')
    queue.put_nowait(f'data: {json.dumps({"type": "done", "run_id": run_id})}\n\n')
    queue.put_nowait(None)


_MOCK_TASK = "orchestra_tprm.server.app._execute_graph_task"


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch(_MOCK_TASK, new=_noop_graph_task)
def test_run_endpoint_accepts_vendor_mode() -> None:
    response = client.post(
        "/run",
        json={"mode": "vendor", "subject_name": "Acme", "packet_path": "/tmp/acme"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "run_id" in body
    assert body["status"] == "accepted"
    assert len(body["run_id"]) > 0


@patch(_MOCK_TASK, new=_noop_graph_task)
def test_run_endpoint_accepts_ma_mode() -> None:
    response = client.post(
        "/run",
        json={"mode": "ma", "subject_name": "TargetCorp", "packet_path": "/tmp/target"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "run_id" in body
    assert body["status"] == "accepted"


def test_run_endpoint_rejects_invalid_mode() -> None:
    response = client.post(
        "/run",
        json={"mode": "invalid", "subject_name": "X", "packet_path": "/tmp/x"},
    )
    assert response.status_code == 422  # Pydantic validation error


def test_events_endpoint_returns_404_for_unknown_run() -> None:
    """Unknown run_id should return 404, not a stale SSE stream."""
    response = client.get("/events/nonexistent-run-id-xyz")
    assert response.status_code == 404


@patch(_MOCK_TASK, new=_noop_graph_task)
def test_run_is_listed_after_launch(tmp_path) -> None:
    """A launched run must appear in GET /runs immediately."""
    response = client.post(
        "/run",
        json={"mode": "vendor", "subject_name": "TestCorp", "packet_path": str(tmp_path)},
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]

    runs = client.get("/runs").json()["runs"]
    assert run_id in runs
    assert runs[run_id]["mode"] == "vendor"
    assert runs[run_id]["subject_name"] == "TestCorp"


@patch(_MOCK_TASK, new=_noop_graph_task)
def test_run_returns_unique_ids() -> None:
    """Each POST /run must produce a distinct run_id."""
    ids = set()
    for _ in range(3):
        r = client.post(
            "/run",
            json={"mode": "vendor", "subject_name": "X", "packet_path": "/tmp/x"},
        )
        ids.add(r.json()["run_id"])
    assert len(ids) == 3
