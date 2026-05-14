"""W-2: safe_specialist wraps a specialist; on exception it returns a
critical/agent-error Finding instead of raising.
W-3: BaseTPRMAgent retries once with a 'compliance review context' prefix
when a SAFETY-flagged response yields no content; emits a filter-suppressed
Finding if still empty."""
from __future__ import annotations

import pytest

from orchestra.core.context import ExecutionContext
from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM
from orchestra_tprm.agents.base import BaseTPRMAgent, safe_specialist
from orchestra_tprm.schemas import Finding


class _DummyAgent(BaseTPRMAgent):
    name = "DummyAgent"

    async def _emit_findings(self, ctx) -> list[Finding]:
        text = await self._call_llm(ctx, prompt="analyze this")
        return [
            Finding(
                agent=self.name,
                category="dummy",
                severity="low",
                summary=text or "",
            )
        ]


@pytest.mark.asyncio
async def test_safe_specialist_converts_exception_to_critical_finding():
    class _Boom(BaseTPRMAgent):
        name = "BoomAgent"

        async def _emit_findings(self, ctx):
            raise RuntimeError("kaboom")

    wrapped = safe_specialist(_Boom())
    findings = await wrapped(ExecutionContext(provider=ScriptedLLM([])))
    assert len(findings) == 1
    assert findings[0].agent == "BoomAgent"
    assert findings[0].severity == "critical"
    assert findings[0].category == "agent-error"
    assert "kaboom" in findings[0].summary


@pytest.mark.asyncio
async def test_safety_retry_succeeds_on_second_call():
    """First call returns SAFETY/empty; second call (with compliance prefix) returns content."""
    llm = ScriptedLLM(
        [
            LLMResponse(content="", finish_reason="safety"),
            LLMResponse(content="reviewed: liability cap"),
        ]
    )
    agent = _DummyAgent()
    ctx = ExecutionContext(provider=llm)
    findings = await agent.run(ctx)
    assert findings[0].summary == "reviewed: liability cap"
    assert len(llm._call_log) == 2
    # Second call must have the compliance prefix
    second = llm._call_log[1]["messages"][-1].content
    assert "compliance review context" in second.lower()


@pytest.mark.asyncio
async def test_safety_retry_emits_filter_suppressed_when_still_empty():
    llm = ScriptedLLM(
        [
            LLMResponse(content="", finish_reason="safety"),
            LLMResponse(content="", finish_reason="safety"),
        ]
    )
    agent = _DummyAgent()
    ctx = ExecutionContext(provider=llm)
    findings = await agent.run(ctx)
    assert len(findings) == 1
    assert findings[0].category == "filter-suppressed"
    assert findings[0].severity == "medium"
