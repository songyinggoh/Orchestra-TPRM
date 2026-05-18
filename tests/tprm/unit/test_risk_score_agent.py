"""Unit tests for RiskScoreAgent: deterministic math + LLM rationale + fallback."""
from __future__ import annotations

import json

import pytest

from orchestra.core.context import ExecutionContext
from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM

from orchestra_tprm.agents.risk_score import RiskScoreAgent
from orchestra_tprm.schemas import Finding


_POLICY = {
    "weights": {"low": 1, "medium": 3, "high": 7, "critical": 15},
    "risk_score_thresholds": {"green_max": 30, "amber_max": 69},
}


def _ctx(provider, *, findings):
    ctx = ExecutionContext(provider=provider)
    ctx.state = {"findings": findings, "subject_name": "HashiCorp"}
    return ctx


async def test_empty_findings_yields_zero_green() -> None:
    llm = ScriptedLLM([])  # never invoked because no drivers
    agent = RiskScoreAgent(policy=_POLICY, model="gemini-2.5-flash")
    ctx = _ctx(llm, findings=[])
    result = await agent.run(ctx)
    rs = result["risk_assessment"]
    assert rs.overall == 0
    assert rs.verdict == "green"
    assert rs.top_risk_drivers == []


async def test_all_critical_yields_high_score_red() -> None:
    findings = [
        Finding(agent="security", category="x", severity="critical", summary="s")
        for _ in range(3)
    ]
    llm = ScriptedLLM([LLMResponse(content=json.dumps({
        "explanation": "All three critical security gaps.",
        "driver_one_liners": ["A", "B", "C"],
    }))])
    agent = RiskScoreAgent(policy=_POLICY, model="gemini-2.5-flash")
    result = await agent.run(_ctx(llm, findings=findings))
    rs = result["risk_assessment"]
    assert rs.overall == 100
    assert rs.verdict == "red"
    assert len(rs.top_risk_drivers) == 3
    assert rs.top_risk_drivers[0].one_liner == "A"


async def test_mixed_severities_math_correct() -> None:
    # weights: low=1, medium=3, high=7, critical=15 → max possible = 4 * 15 = 60
    # sum = 1 + 3 + 7 + 15 = 26 → 100*26/60 = 43 → amber
    findings = [
        Finding(agent="legal",    category="a", severity="low",      summary="a"),
        Finding(agent="security", category="b", severity="medium",   summary="b"),
        Finding(agent="code",     category="c", severity="high",     summary="c"),
        Finding(agent="esg",      category="d", severity="critical", summary="d"),
    ]
    llm = ScriptedLLM([LLMResponse(content=json.dumps({
        "explanation": "Mixed risk profile.",
        "driver_one_liners": ["esg crit", "code high", "sec medium"],
    }))])
    agent = RiskScoreAgent(policy=_POLICY, model="gemini-2.5-flash")
    result = await agent.run(_ctx(llm, findings=findings))
    rs = result["risk_assessment"]
    assert rs.overall == 43
    assert rs.verdict == "amber"
    assert set(rs.dimensions.keys()) == {"legal", "security", "code", "esg"}
    # Per-dimension: each has 1 finding; dim score = 100 * weight / (1 * 15)
    assert rs.dimensions["esg"] == 100  # critical / critical
    assert rs.dimensions["legal"] == round(100 * 1 / 15)


async def test_llm_failure_uses_fallback_explanation() -> None:
    # ScriptedLLM with empty queue raises when called → agent must catch and fall back.
    findings = [
        Finding(agent="security", category="x", severity="high", summary="SOC2 gap"),
    ]
    llm = ScriptedLLM([])  # no responses queued — raises on first call
    agent = RiskScoreAgent(policy=_POLICY, model="gemini-2.5-flash")
    result = await agent.run(_ctx(llm, findings=findings))
    rs = result["risk_assessment"]
    assert rs.overall > 0
    # Fallback explanation references the top dimension
    assert "security" in rs.explanation.lower()
    assert rs.top_risk_drivers[0].one_liner.startswith("SOC2 gap")


async def test_verdict_thresholds_match_policy() -> None:
    # 30 overall = green (≤ green_max)
    # 31 overall = amber
    # 70 overall = red (≥ amber_max + 1)
    agent = RiskScoreAgent(policy=_POLICY, model="gemini-2.5-flash")
    assert agent._verdict(30) == "green"
    assert agent._verdict(31) == "amber"
    assert agent._verdict(69) == "amber"
    assert agent._verdict(70) == "red"
