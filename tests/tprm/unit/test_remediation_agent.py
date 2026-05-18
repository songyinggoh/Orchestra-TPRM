# tests/tprm/unit/test_remediation_agent.py
"""Unit tests for RemediationAgent: skip predicate + mode-aware prompt."""
from __future__ import annotations

import json

from orchestra.core.context import ExecutionContext
from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM

from orchestra_tprm.agents.remediation import RemediationAgent, should_run_remediation
from orchestra_tprm.schemas import Finding


def _ctx(provider, *, findings, verdict, ic_recommendation=None):
    ctx = ExecutionContext(provider=provider)
    ctx.state = {
        "findings": findings,
        "policy_verdict": verdict,
        "ic_memo": {"recommendation": ic_recommendation} if ic_recommendation else {},
        "subject_name": "HashiCorp",
    }
    return ctx


def test_skip_when_approve_and_no_medium_plus() -> None:
    findings = [Finding(agent="legal", category="x", severity="low", summary="trivial")]
    state = {"findings": findings, "policy_verdict": "approve", "ic_memo": {}}
    assert should_run_remediation(state) is False


def test_run_when_approve_but_has_medium() -> None:
    findings = [Finding(agent="legal", category="x", severity="medium", summary="m")]
    state = {"findings": findings, "policy_verdict": "approve", "ic_memo": {}}
    assert should_run_remediation(state) is True


def test_run_when_reject_verdict() -> None:
    state = {"findings": [], "policy_verdict": "reject", "ic_memo": {}}
    assert should_run_remediation(state) is True


def test_skip_when_ma_proceed_and_no_medium_plus() -> None:
    state = {
        "findings": [Finding(agent="x", category="x", severity="low", summary="x")],
        "policy_verdict": "",
        "ic_memo": {"recommendation": "proceed"},
    }
    assert should_run_remediation(state) is False


async def test_vendor_framing_generates_vendor_owner_items() -> None:
    findings = [
        Finding(agent="security", category="soc2-gap", severity="high", summary="SOC2 missing"),
    ]
    llm = ScriptedLLM([LLMResponse(content=json.dumps({
        "items": [
            {
                "finding_id": findings[0].id,
                "action": "Demand SOC2 Type II report before signing",
                "owner": "vendor",
                "priority": "P0",
                "leverage": "MSA security warranty clause",
                "est_effort_days": 30,
            }
        ],
        "horizon_days": 30,
        "summary": "Vendor must close SOC2 gap before contract execution.",
    }))])
    agent = RemediationAgent(mode="vendor", model="gemini-2.5-flash")
    ctx = _ctx(llm, findings=findings, verdict="conditional-approve")
    result = await agent.run(ctx)
    plan = result["remediation_plan"]
    assert len(plan.items) == 1
    assert plan.items[0].owner == "vendor"
    assert plan.items[0].priority == "P0"
    assert plan.horizon_days == 30


async def test_ma_framing_generates_buyer_owner_items() -> None:
    findings = [
        Finding(agent="legal", category="ip-assignment", severity="high", summary="IP gap"),
    ]
    llm = ScriptedLLM([LLMResponse(content=json.dumps({
        "items": [
            {
                "finding_id": findings[0].id,
                "action": "Negotiate IP-rep indemnity with 18-month survival",
                "owner": "buyer",
                "priority": "P1",
                "leverage": "SPA section 8.2 reps & warranties",
                "est_effort_days": 60,
            }
        ],
        "horizon_days": 60,
        "summary": "Address IP gap via SPA reps and indemnity.",
    }))])
    agent = RemediationAgent(mode="ma", model="gemini-2.5-flash")
    ctx = _ctx(llm, findings=findings, verdict="", ic_recommendation="reprice")
    result = await agent.run(ctx)
    plan = result["remediation_plan"]
    assert plan.items[0].owner == "buyer"


async def test_skip_emits_empty_plan_with_summary() -> None:
    findings = [Finding(agent="legal", category="x", severity="low", summary="ok")]
    llm = ScriptedLLM([])  # never called when skipped
    agent = RemediationAgent(mode="vendor", model="gemini-2.5-flash")
    ctx = _ctx(llm, findings=findings, verdict="approve")
    result = await agent.run(ctx)
    plan = result["remediation_plan"]
    assert plan.items == []
    assert "clean" in plan.summary.lower()


async def test_llm_parse_error_returns_empty_plan() -> None:
    findings = [Finding(agent="security", category="x", severity="high", summary="bad")]
    llm = ScriptedLLM([LLMResponse(content="not-json-at-all")])
    agent = RemediationAgent(mode="vendor", model="gemini-2.5-flash")
    ctx = _ctx(llm, findings=findings, verdict="conditional-approve")
    result = await agent.run(ctx)
    plan = result["remediation_plan"]
    assert plan.items == []
    assert "parse" in plan.summary.lower() or "unavailable" in plan.summary.lower()
