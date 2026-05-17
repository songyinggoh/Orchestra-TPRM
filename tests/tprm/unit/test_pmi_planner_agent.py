"""Unit tests for PMIPlannerAgent (Plan 05 / REQ-10)."""
from __future__ import annotations

import json

from orchestra.core.context import ExecutionContext
from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM
from orchestra_tprm.agents.pmi_planner import PMIPlannerAgent
from orchestra_tprm.schemas import Finding


async def test_empty_findings_returns_empty_plan() -> None:
    """No findings → empty PMIPlan with explanatory summary."""
    agent = PMIPlannerAgent()
    out = await agent({"findings": []})
    assert out["pmi_plan"]["items"] == []
    assert "No PMI actions" in out["pmi_plan"]["summary"]


async def test_no_provider_fallback_assigns_correct_tiers() -> None:
    """Without ctx.provider, deterministic fallback uses _tier_for_finding rules."""
    agent = PMIPlannerAgent()
    findings = [
        Finding(
            agent="X",
            category="gpl",
            severity="critical",
            summary="GPL detected",
            workstream="tech",
            ic_decision="deal-stopper",
        ).model_dump(),
        Finding(
            agent="Y",
            category="wage-lit",
            severity="high",
            summary="Wage litigation",
            workstream="hr",
            ic_decision="price-adjustment",
        ).model_dump(),
        Finding(
            agent="Z",
            category="nrr-low",
            severity="medium",
            summary="NRR low",
            workstream="financial",
            ic_decision="price-adjustment",
        ).model_dump(),
    ]
    out = await agent({"findings": findings})
    items = out["pmi_plan"]["items"]
    assert len(items) == 3

    tier_by_ws = {it["workstream"]: it["deadline_tier"] for it in items}
    # Per CONTEXT.md PMI Deadline Tier Assignment Logic
    assert tier_by_ws["tech"] == "day-30"        # critical security/tech OR deal-stopper
    assert tier_by_ws["hr"] == "day-60"          # HR retention
    assert tier_by_ws["financial"] == "day-100"  # process/operational

    # Owner mapping
    owner_by_ws = {it["workstream"]: it["owner"] for it in items}
    assert owner_by_ws["tech"] == "CIO"
    assert owner_by_ws["hr"] == "CHRO"
    assert owner_by_ws["financial"] == "CFO"


async def test_llm_happy_path_returns_validated_plan() -> None:
    """ScriptedLLM returns valid JSON → PMIPlan items pass through unchanged."""
    agent = PMIPlannerAgent()
    findings = [
        Finding(
            agent="X",
            category="c",
            severity="high",
            summary="X",
            workstream="tech",
            ic_decision="deal-stopper",
        ).model_dump(),
    ]
    llm = ScriptedLLM([LLMResponse(content=json.dumps({
        "summary": "Integration roadmap",
        "items": [
            {"workstream": "tech", "action": "Replace GPL component", "deadline_tier": "day-30", "owner": "CIO", "dependency": None},
            {"workstream": "hr", "action": "Issue retention packages", "deadline_tier": "day-60", "owner": "CHRO", "dependency": "tech-30"},
        ],
    }))])
    ctx = ExecutionContext(provider=llm)
    out = await agent({"findings": findings, "subject_name": "T"}, ctx=ctx)
    assert out["pmi_plan"]["summary"] == "Integration roadmap"
    assert len(out["pmi_plan"]["items"]) == 2
    assert out["pmi_plan"]["items"][1]["dependency"] == "tech-30"


async def test_invalid_workstream_or_tier_filtered_out() -> None:
    """Unknown workstream values are dropped; unknown tiers are clamped to day-100."""
    agent = PMIPlannerAgent()
    findings = [
        Finding(
            agent="X",
            category="c",
            severity="high",
            summary="X",
            workstream="tech",
            ic_decision="deal-stopper",
        ).model_dump(),
    ]
    llm = ScriptedLLM([LLMResponse(content=json.dumps({
        "summary": "x",
        "items": [
            {"workstream": "BOGUS_WS", "action": "X", "deadline_tier": "day-30", "owner": "X"},
            {"workstream": "tech", "action": "valid", "deadline_tier": "century-1000", "owner": "CIO"},
            {"workstream": "hr", "action": "", "deadline_tier": "day-60", "owner": "CHRO"},  # empty action → dropped
        ],
    }))])
    ctx = ExecutionContext(provider=llm)
    out = await agent({"findings": findings}, ctx=ctx)
    items = out["pmi_plan"]["items"]
    # BOGUS_WS dropped, empty action dropped, century-1000 tier clamped → only one item remains
    assert len(items) == 1
    assert items[0]["workstream"] == "tech"
    assert items[0]["deadline_tier"] == "day-100"  # clamped default
