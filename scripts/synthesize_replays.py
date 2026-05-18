"""Synthesize replay JSONL files for Acme (vendor) and HashiCorp (M&A)
demos when live Gemini quota is unavailable.

The replay JSONL format is line-delimited LLMCalled events from
orchestra.storage.events. ReplayProvider plays them back in sequence
(falling back from prompt_hash matching to FIFO when hashes are absent).

We reuse the test fixtures _vendor_responses() + _ma_responses()
already validated for the 3-agent delta pipeline:
  Router → [specialists parallel] → risk_score → policy → remediation → coordinator
  (+ pmi_planner in M&A mode after coordinator)

Run from the Orchestra repo root:
  python scripts/synthesize_replays.py
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests" / "tprm" / "integration"))

# Import fixtures from the integration conftest
from conftest import _vendor_responses, _ma_responses  # type: ignore[import-not-found]


def _make_event(seq: int, content: str, model: str = "gemini-2.5-flash") -> dict:
    """Build a single LLMCalled event with no prompt_hash so ReplayProvider
    falls back to sequential pointer playback."""
    return {
        "event_id": uuid.uuid4().hex,
        "run_id": "recorded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sequence": seq,
        "event_type": "llm.called",
        "schema_version": 1,
        "node_id": "agent",
        "agent_name": "agent",
        "model": model,
        "content": content,
        "tool_calls": [],
        "input_tokens": len(content) // 4 or 1,
        "output_tokens": len(content) // 4 or 1,
        "cost_usd": 0.0,
        "duration_ms": 1234.0,
        "finish_reason": "stop",
        "prompt_hash": "",  # empty → ReplayProvider uses sequential FIFO
    }


def write_jsonl(responses, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for seq, resp in enumerate(responses):
            evt = _make_event(seq, resp.content)
            f.write(json.dumps(evt, default=str) + "\n")
    print(f"wrote {len(responses)} events to {output_path}")


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    write_jsonl(_vendor_responses(), root / "examples" / "tprm" / "acme" / "replay.jsonl")
    write_jsonl(_ma_responses(), root / "examples" / "tprm" / "hashicorp" / "replay.jsonl")


if __name__ == "__main__":
    main()
