"""Smoke test: CLI replay mode runs end-to-end without live LLM calls.

Writes a minimal JSONL fixture (LLMCalled events returning empty findings)
and verifies that ``--local --replay`` completes with exit_code 0.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from typer.testing import CliRunner

from orchestra_tprm.cli import app


def _make_llm_called(run_id: str, node_id: str, content: str) -> dict:
    return {
        "event_id": uuid.uuid4().hex,
        "run_id": run_id,
        "timestamp": "2026-05-17T00:00:00+00:00",
        "sequence": 0,
        "event_type": "llm.called",
        "schema_version": 1,
        "node_id": node_id,
        "agent_name": node_id,
        "model": "gemini-2.5-flash",
        "content": content,
        "tool_calls": [],
        "input_tokens": 10,
        "output_tokens": 5,
        "cost_usd": 0.0,
        "duration_ms": 1.0,
        "finish_reason": "stop",
    }


def _write_replay_jsonl(path: Path, run_id: str, nodes: list[str], content: str) -> None:
    lines = [json.dumps(_make_llm_called(run_id, n, content)) for n in nodes]
    path.write_text("\n".join(lines), encoding="utf-8")


# 200 events is generous enough to cover all multi-turn agent loops in vendor mode
# (matches the 60-response pool in _stub_local_provider * safety margin)
_VENDOR_CALL_COUNT = 200


def test_cli_replay_vendor_local(tmp_path: Path):
    run_id = uuid.uuid4().hex
    replay_path = tmp_path / "vendor_replay.jsonl"
    # node_id doesn't affect replay ordering — provider replays sequentially
    _write_replay_jsonl(replay_path, run_id, ["agent"] * _VENDOR_CALL_COUNT, content="[]")

    out_path = tmp_path / "out.json"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--mode", "vendor",
            "--packet", "examples/tprm/acme",
            "--local",
            "--replay", str(replay_path),
            "--out", str(out_path),
            "--no-dashboard",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(out_path.read_text())
    assert payload["mode"] == "vendor"
