"""Unit tests for SaaSMetricsAgent (Plan 04 / REQ-07).

All LLM calls mocked via ScriptedLLM — no live Gemini calls.
"""
from __future__ import annotations

import json
from pathlib import Path

from orchestra.core.context import ExecutionContext
from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM
from orchestra_tprm.agents.specialists.saas_metrics import SaaSMetricsAgent


def _make_ctx(provider, *, file_uris=None, routing=None) -> ExecutionContext:
    ctx = ExecutionContext(provider=provider)
    ctx.state = {
        "subject_name": "TargetCorp",
        "file_uris": file_uris or {},
        "routing": routing or {},
        "mode": "ma",
    }
    return ctx


async def test_no_docs_routed_emits_informational_finding() -> None:
    """No documents routed to SaaSMetricsAgent → single informational Finding."""
    agent = SaaSMetricsAgent(model="gemini-2.5-flash")
    ctx = _make_ctx(ScriptedLLM([]), routing={}, file_uris={})
    findings = await agent.run(ctx)
    assert len(findings) == 1
    f = findings[0]
    assert f.category == "saas-metrics-no-docs"
    assert f.workstream == "financial"
    assert f.ic_decision == "post-close-monitoring"
    assert f.severity == "low"


async def test_nrr_below_90_emits_deal_stopper(tmp_path: Path) -> None:
    """LLM returns NRR=88 with ic_decision='deal-stopper' — agent surfaces it."""
    doc = tmp_path / "investor_deck.txt"
    doc.write_text("ARR $45M, NRR 88%, logo retention 82%")
    agent = SaaSMetricsAgent(model="gemini-2.5-flash")
    llm = ScriptedLLM([LLMResponse(content=json.dumps([
        {
            "metric": "nrr",
            "value_pct": "88",
            "threshold_breached": True,
            "severity": "critical",
            "ic_decision": "deal-stopper",
            "exposure_usd_low": 0,
            "exposure_usd_high": 5_000_000,
            "summary": "NRR 88% below 90% threshold — deal-stopper",
            "citation_page": 4,
        }
    ]))])
    ctx = _make_ctx(
        llm,
        file_uris={"investor_deck.txt": f"local://{doc.as_posix()}"},
        routing={"SaaSMetricsAgent": ["investor_deck.txt"]},
    )
    findings = await agent.run(ctx)
    assert len(findings) == 1
    f = findings[0]
    assert f.ic_decision == "deal-stopper"
    assert f.workstream == "financial"
    assert f.exposure_usd_range == (0, 5_000_000)
    assert f.severity == "critical"


async def test_invalid_ic_decision_clamped_to_post_close(tmp_path: Path) -> None:
    """Unknown ic_decision strings from the LLM are clamped to post-close-monitoring."""
    doc = tmp_path / "deck.txt"
    doc.write_text("metrics")
    agent = SaaSMetricsAgent(model="gemini-2.5-flash")
    llm = ScriptedLLM([LLMResponse(content=json.dumps([
        {
            "metric": "rule-of-40",
            "value_pct": "35",
            "threshold_breached": False,
            "severity": "low",
            "ic_decision": "completely-bogus-label",
            "summary": "Rule of 40 = 35 (acceptable)",
        }
    ]))])
    ctx = _make_ctx(
        llm,
        file_uris={"deck.txt": f"local://{doc.as_posix()}"},
        routing={"SaaSMetricsAgent": ["deck.txt"]},
    )
    findings = await agent.run(ctx)
    assert len(findings) == 1
    assert findings[0].ic_decision == "post-close-monitoring"


async def test_malformed_json_emits_parse_error(tmp_path: Path) -> None:
    """LLM returns non-JSON → parse-error Finding (critical severity)."""
    doc = tmp_path / "x.txt"
    doc.write_text("blob")
    agent = SaaSMetricsAgent(model="gemini-2.5-flash")
    llm = ScriptedLLM([LLMResponse(content="this is not JSON at all")])
    ctx = _make_ctx(
        llm,
        file_uris={"x.txt": f"local://{doc.as_posix()}"},
        routing={"SaaSMetricsAgent": ["x.txt"]},
    )
    findings = await agent.run(ctx)
    assert len(findings) == 1
    assert findings[0].category == "parse-error"
    assert findings[0].severity == "critical"
    assert findings[0].workstream == "financial"
