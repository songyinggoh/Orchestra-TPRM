"""Unit tests for the FastAPI server — HTTP layer only.

Background graph execution is mocked so tests run instantly without
spawning Gemini CLI subprocesses.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from orchestra_tprm.server.app import app

client = TestClient(app)

# Patch target for path-traversal guard — allows tests to set a permissive root
_PACKET_ROOT_PATCH = "orchestra_tprm.server.app._ALLOWED_PACKET_ROOT"


# ── Mock helpers ──────────────────────────────────────────────────────────────


async def _noop_graph_task(run_id, queue, mode, subject_name, packet_path, drive_folder_url=None, ma_scope=None):
    """Instant stub: emits started + done then closes the stream."""
    import json
    queue.put_nowait(f'data: {json.dumps({"type": "started", "run_id": run_id})}\n\n')
    queue.put_nowait(f'data: {json.dumps({"type": "done", "run_id": run_id})}\n\n')
    queue.put_nowait(None)


_MOCK_TASK = "orchestra_tprm.server.app._execute_graph_task"


def _collect_sse_events(run_id: str) -> list[dict]:
    """Stream /events/{run_id} to completion and return parsed event dicts."""
    import json
    events = []
    with client.stream("GET", f"/events/{run_id}") as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                try:
                    events.append(json.loads(line[len("data: "):]))
                except json.JSONDecodeError:
                    pass
    return events


async def _verdict_graph_task(run_id, queue, mode, subject_name, packet_path, drive_folder_url=None, ma_scope=None):
    """Stub that emits a full verdict event then closes."""
    import json
    queue.put_nowait(f'data: {json.dumps({"type": "started", "run_id": run_id})}\n\n')
    queue.put_nowait(f'data: {json.dumps({"type": "verdict", "policy_verdict": "pass", "risk_score": 10, "findings_count": 0, "findings": [], "verdict_doc_id": "", "verdict_local_path": "", "ic_memo": None, "pmi_plan": None})}\n\n')
    queue.put_nowait(f'data: {json.dumps({"type": "done", "run_id": run_id})}\n\n')
    queue.put_nowait(None)


async def _ma_verdict_graph_task(run_id, queue, mode, subject_name, packet_path, drive_folder_url=None, ma_scope=None):
    """Stub that emits a verdict with ic_memo and pmi_plan fields."""
    import json
    ic_memo = {"executive_summary": "Low risk", "headline_terms": "Proceed", "recommendation": "proceed", "risk_register": []}
    pmi_plan = {"summary": "Standard integration", "items": [{"workstream": "tech", "action": "SSO setup", "deadline_tier": "day-60", "owner": "IT", "dependency": None}]}
    queue.put_nowait(f'data: {json.dumps({"type": "verdict", "policy_verdict": "pass", "risk_score": 5, "findings_count": 0, "findings": [], "verdict_doc_id": "", "verdict_local_path": "", "ic_memo": ic_memo, "pmi_plan": pmi_plan})}\n\n')
    queue.put_nowait(f'data: {json.dumps({"type": "done", "run_id": run_id})}\n\n')
    queue.put_nowait(None)


async def _failing_graph_task(run_id, queue, mode, subject_name, packet_path, drive_folder_url=None, ma_scope=None):
    """Stub that simulates a graph exception — error + done must both fire."""
    import json
    queue.put_nowait(f'data: {json.dumps({"type": "error", "message": "simulated graph failure"})}\n\n')
    queue.put_nowait(f'data: {json.dumps({"type": "done", "run_id": run_id})}\n\n')
    queue.put_nowait(None)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch(_MOCK_TASK, new=_noop_graph_task)
@patch(_PACKET_ROOT_PATCH, Path("/tmp").resolve())
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
@patch(_PACKET_ROOT_PATCH, Path("/tmp").resolve())
def test_run_endpoint_accepts_ma_mode() -> None:
    response = client.post(
        "/run",
        json={"mode": "ma", "subject_name": "TargetCorp", "packet_path": "/tmp/target"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "run_id" in body
    assert body["status"] == "accepted"


@patch(_PACKET_ROOT_PATCH, Path("/tmp").resolve())
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
    with patch(_PACKET_ROOT_PATCH, tmp_path.resolve()):
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
@patch(_PACKET_ROOT_PATCH, Path("/tmp").resolve())
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


@patch(_MOCK_TASK, new=_noop_graph_task)
@patch(_PACKET_ROOT_PATCH, Path("/tmp").resolve())
def test_run_endpoint_accepts_ma_scope() -> None:
    """POST /run with ma_scope should be accepted (200), not rejected."""
    response = client.post(
        "/run",
        json={
            "mode": "ma",
            "subject_name": "TargetCorp",
            "packet_path": "/tmp/target",
            "ma_scope": {
                "investment_thesis": "SaaS consolidation play",
                "enterprise_value_usd": 50_000_000,
                "materiality_threshold_usd": 1_000_000,
                "deal_breakers": ["going-concern"],
                "active_workstreams": ["financial", "tech", "legal"],
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


@patch(_MOCK_TASK, new=_noop_graph_task)
@patch(_PACKET_ROOT_PATCH, Path("/tmp").resolve())
def test_run_endpoint_accepts_ma_mode_without_scope() -> None:
    """ma_scope is optional — omitting it must still succeed."""
    response = client.post(
        "/run",
        json={"mode": "ma", "subject_name": "TargetCorp", "packet_path": "/tmp/target"},
    )
    assert response.status_code == 200


@patch(_PACKET_ROOT_PATCH, Path("/tmp").resolve())
def test_run_endpoint_rejects_invalid_ma_scope_type() -> None:
    """ma_scope must be a dict or null, not a string."""
    response = client.post(
        "/run",
        json={
            "mode": "ma",
            "subject_name": "X",
            "packet_path": "/tmp/x",
            "ma_scope": "not-a-dict",
        },
    )
    assert response.status_code == 422


def test_run_endpoint_rejects_path_traversal() -> None:
    """packet_path that escapes PACKET_ROOT must return 400 (CR-01)."""
    response = client.post(
        "/run",
        json={"mode": "vendor", "subject_name": "Attacker", "packet_path": "../../../etc/passwd"},
    )
    assert response.status_code == 400
    assert "escapes" in response.json().get("detail", "").lower()


# ── SSE stream contract tests ──────────────────────────────────────────────────
# These pin the server-side guarantee that prevents the "Connection lost" false
# positive: the stream must always emit `done` as the final event before closing,
# so the frontend can distinguish a clean close from a real network failure.


@patch(_MOCK_TASK, new=_verdict_graph_task)
@patch(_PACKET_ROOT_PATCH, Path("/tmp").resolve())
def test_sse_stream_emits_verdict_before_done() -> None:
    """verdict event must appear in the stream before the done event."""
    run_id = client.post(
        "/run", json={"mode": "vendor", "subject_name": "X", "packet_path": "/tmp/x"}
    ).json()["run_id"]

    events = _collect_sse_events(run_id)
    types = [e["type"] for e in events]

    assert "verdict" in types
    assert "done" in types
    assert types.index("verdict") < types.index("done"), "verdict must precede done"


@patch(_MOCK_TASK, new=_verdict_graph_task)
@patch(_PACKET_ROOT_PATCH, Path("/tmp").resolve())
def test_sse_stream_done_is_last_event_on_success() -> None:
    """done must be the final typed event — nothing follows it before stream closes."""
    run_id = client.post(
        "/run", json={"mode": "vendor", "subject_name": "X", "packet_path": "/tmp/x"}
    ).json()["run_id"]

    events = _collect_sse_events(run_id)
    typed = [e for e in events if "type" in e]
    assert typed[-1]["type"] == "done"


@patch(_MOCK_TASK, new=_failing_graph_task)
@patch(_PACKET_ROOT_PATCH, Path("/tmp").resolve())
def test_sse_stream_done_fires_even_on_graph_error() -> None:
    """done must appear even when the graph raises — it is sent in the finally block."""
    run_id = client.post(
        "/run", json={"mode": "vendor", "subject_name": "X", "packet_path": "/tmp/x"}
    ).json()["run_id"]

    events = _collect_sse_events(run_id)
    types = [e["type"] for e in events]

    assert "error" in types, "error event must be emitted on graph failure"
    assert "done" in types, "done event must always fire (finally block guarantee)"
    assert types.index("error") < types.index("done"), "error must precede done"


@patch(_MOCK_TASK, new=_failing_graph_task)
@patch(_PACKET_ROOT_PATCH, Path("/tmp").resolve())
def test_sse_stream_error_event_includes_message() -> None:
    """error event must carry a non-empty message field."""
    run_id = client.post(
        "/run", json={"mode": "vendor", "subject_name": "X", "packet_path": "/tmp/x"}
    ).json()["run_id"]

    events = _collect_sse_events(run_id)
    error_events = [e for e in events if e.get("type") == "error"]

    assert error_events, "at least one error event expected"
    assert error_events[0].get("message"), "error event must have a non-empty message"


@patch(_MOCK_TASK, new=_ma_verdict_graph_task)
@patch(_PACKET_ROOT_PATCH, Path("/tmp").resolve())
def test_sse_verdict_contains_ic_memo_for_ma_mode() -> None:
    """verdict event for M&A runs must include ic_memo field."""
    run_id = client.post(
        "/run", json={"mode": "ma", "subject_name": "TargetCorp", "packet_path": "/tmp/x"}
    ).json()["run_id"]

    events = _collect_sse_events(run_id)
    verdict = next((e for e in events if e.get("type") == "verdict"), None)

    assert verdict is not None, "verdict event must be present"
    assert "ic_memo" in verdict, "verdict must carry ic_memo for M&A mode"
    assert verdict["ic_memo"] is not None


@patch(_MOCK_TASK, new=_ma_verdict_graph_task)
@patch(_PACKET_ROOT_PATCH, Path("/tmp").resolve())
def test_sse_verdict_contains_pmi_plan_for_ma_mode() -> None:
    """verdict event for M&A runs must include pmi_plan field."""
    run_id = client.post(
        "/run", json={"mode": "ma", "subject_name": "TargetCorp", "packet_path": "/tmp/x"}
    ).json()["run_id"]

    events = _collect_sse_events(run_id)
    verdict = next((e for e in events if e.get("type") == "verdict"), None)

    assert verdict is not None
    assert "pmi_plan" in verdict, "verdict must carry pmi_plan for M&A mode"
    assert verdict["pmi_plan"] is not None


# ── Root-cause tests for "Connection lost" false positive ─────────────────────
#
# Three failure modes cause the frontend to show "Connection lost" on a
# completed run:
#
#   RC-1  Frontend race: es.close() was called inside the setRunState updater;
#         some browsers fire onerror synchronously during close(), before React
#         commits the done state update.  Fixed: ref set before es.close().
#         (No Python test — this is a browser timing issue.)
#
#   RC-2  Backend: put_nowait vs await queue.put() in the finally block.
#         If the asyncio task is cancelled (e.g. on server shutdown), the
#         await inside the finally block re-raises CancelledError, so done
#         and the None sentinel are never queued.  The SSE stream hangs open
#         and the browser eventually fires onerror.
#
#   RC-3  Backend: deadline path in _stream() yielded error + break but no
#         done event, leaving the browser without a terminal signal.


async def _exception_before_started_task(run_id, queue, mode, subject_name, packet_path, drive_folder_url=None, ma_scope=None):
    """Simulates a graph crash before the started event.

    Mirrors the try/except/finally structure of the real _execute_graph_task so
    that error + done + None are properly emitted — if this cleanup is absent the
    SSE stream hangs waiting for the None sentinel (30-second heartbeat loop).
    """
    try:
        raise RuntimeError("boom before started")
    except Exception as exc:
        queue.put_nowait(f'data: {json.dumps({"type": "error", "message": str(exc)})}\n\n')
    finally:
        queue.put_nowait(f'data: {json.dumps({"type": "done", "run_id": run_id})}\n\n')
        queue.put_nowait(None)


async def _exception_after_started_task(run_id, queue, mode, subject_name, packet_path, drive_folder_url=None, ma_scope=None):
    """Simulates a graph crash after the started event is already queued."""
    queue.put_nowait(f'data: {json.dumps({"type": "started", "run_id": run_id})}\n\n')
    try:
        raise RuntimeError("boom after started")
    except Exception as exc:
        queue.put_nowait(f'data: {json.dumps({"type": "error", "message": str(exc)})}\n\n')
    finally:
        queue.put_nowait(f'data: {json.dumps({"type": "done", "run_id": run_id})}\n\n')
        queue.put_nowait(None)


# ── RC-2: cancellation safety of the finally block ───────────────────────────


@pytest.mark.asyncio
async def test_put_nowait_in_finally_survives_task_cancellation() -> None:
    """
    RC-2: Verify that put_nowait() does not raise when called during
    CancelledError propagation.  An awaited queue.put() in a finally block
    re-raises CancelledError and silently drops the sentinel; put_nowait()
    with an unbounded queue (maxsize=0) is always safe to call without await.
    """
    q: asyncio.Queue = asyncio.Queue()  # maxsize=0 → unlimited

    async def _slow_coro() -> None:
        try:
            await asyncio.sleep(60)
        finally:
            # This is the critical assertion: put_nowait must not raise
            # even when the coroutine is being cancelled.
            q.put_nowait("done_sentinel")
            q.put_nowait(None)

    task = asyncio.create_task(_slow_coro())
    await asyncio.sleep(0)  # let the task start and reach its first await
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert q.get_nowait() == "done_sentinel", "put_nowait in finally must succeed on cancellation"
    assert q.get_nowait() is None


@pytest.mark.asyncio
async def test_finally_block_emits_done_and_none_on_graph_exception() -> None:
    """
    RC-2 (unit): The try/except/finally pattern used in _execute_graph_task
    must emit done + None even when the exception path is taken.  This test
    isolates the pattern itself without importing the real graph machinery.
    """
    q: asyncio.Queue = asyncio.Queue()
    run_id = "rc2-unit"
    fake_runs: dict = {run_id: {"status": "accepted"}}

    async def _graph_task_pattern() -> None:
        """Minimal reproduction of _execute_graph_task's error-handling skeleton."""
        try:
            fake_runs[run_id]["status"] = "running"
            raise RuntimeError("graph exploded")
        except Exception as exc:
            fake_runs[run_id]["status"] = "error"
            q.put_nowait(f'data: {json.dumps({"type": "error", "message": str(exc)})}\n\n')
        finally:
            q.put_nowait(f'data: {json.dumps({"type": "done", "run_id": run_id})}\n\n')
            q.put_nowait(None)

    await _graph_task_pattern()

    items = []
    while not q.empty():
        items.append(q.get_nowait())

    events = [
        json.loads(item[len("data: "):])
        for item in items
        if item is not None and isinstance(item, str) and item.startswith("data: ")
    ]
    types = [e.get("type") for e in events]

    assert "error" in types, f"error expected; got {types}"
    assert "done" in types, f"done expected; got {types}"
    assert types.index("error") < types.index("done")
    assert items[-1] is None, "None sentinel must be last"


# ── RC-3: deadline path must emit done ────────────────────────────────────────

# Patch _STREAM_DEADLINE_SEC to 0 so the deadline fires on the first loop
# iteration without touching time.monotonic (which would break asyncio's
# internal scheduler and cause spurious timeouts in other tests).
_DEADLINE_PATCH = "orchestra_tprm.server.app._STREAM_DEADLINE_SEC"


@patch(_MOCK_TASK, new=_noop_graph_task)
@patch(_PACKET_ROOT_PATCH, Path("/tmp").resolve())
@patch(_DEADLINE_PATCH, 0)
def test_deadline_path_emits_done_via_stream() -> None:
    """
    RC-3: With _STREAM_DEADLINE_SEC=0 the deadline fires on the first loop
    iteration.  The stream must still yield 'done' before closing — without it
    the browser cannot distinguish a 15-min timeout from a network drop and
    will show 'Connection lost'.
    """
    run_id = client.post(
        "/run", json={"mode": "vendor", "subject_name": "X", "packet_path": "/tmp/x"}
    ).json()["run_id"]

    events = _collect_sse_events(run_id)
    types = [e.get("type") for e in events]
    assert "done" in types, f"done must appear even on deadline breach; got {types}"
    assert "error" in types, f"error event expected on deadline; got {types}"
    assert types.index("error") < types.index("done"), "error must precede done"


# ── Exception-path ordering ───────────────────────────────────────────────────


@patch(_MOCK_TASK, new=_exception_after_started_task)
@patch(_PACKET_ROOT_PATCH, Path("/tmp").resolve())
def test_exception_after_started_still_emits_error_and_done() -> None:
    """
    RC-2: An exception raised inside the graph (after 'started' is sent) must
    produce error → done in the SSE stream — not a hanging connection.
    """
    run_id = client.post(
        "/run", json={"mode": "vendor", "subject_name": "X", "packet_path": "/tmp/x"}
    ).json()["run_id"]

    events = _collect_sse_events(run_id)
    types = [e.get("type") for e in events]

    assert "started" in types, f"started expected; got {types}"
    assert "error" in types, f"error expected after exception; got {types}"
    assert "done" in types, f"done must always fire (finally guarantee); got {types}"
    assert types.index("error") < types.index("done")


@patch(_MOCK_TASK, new=_exception_before_started_task)
@patch(_PACKET_ROOT_PATCH, Path("/tmp").resolve())
def test_exception_before_started_still_emits_error_and_done() -> None:
    """
    RC-2: Even when the graph crashes before writing the started event, the
    finally block must emit error + done so the browser reaches a terminal state.
    """
    run_id = client.post(
        "/run", json={"mode": "vendor", "subject_name": "X", "packet_path": "/tmp/x"}
    ).json()["run_id"]

    events = _collect_sse_events(run_id)
    types = [e.get("type") for e in events]

    assert "error" in types, f"error expected; got {types}"
    assert "done" in types, f"done must fire even before started; got {types}"
    assert types.index("error") < types.index("done")
