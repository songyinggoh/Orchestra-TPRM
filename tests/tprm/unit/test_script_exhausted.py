"""Boundary tests for ScriptExhaustedError in the TPRM test harness.

Covers:
  - ScriptedLLM with zero responses raises ScriptExhaustedError when called
  - _call_llm propagates ScriptExhaustedError out of BaseTPRMAgent
  - safe_specialist converts ScriptExhaustedError to critical/agent-error Finding
  - assert_all_consumed raises AssertionError on early-exit (unconsumed responses)
  - assert_all_consumed passes silently when all responses consumed exactly
  - _TwoCallAgent with one-response script exhausts on second call;
    safe_specialist wraps the error to a critical Finding
"""
from __future__ import annotations

import pytest

from orchestra.core.context import ExecutionContext
from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM
from orchestra.testing.scripted import ScriptExhaustedError
from orchestra_tprm.agents.base import BaseTPRMAgent, safe_specialist
from orchestra_tprm.schemas import Finding


# ---------------------------------------------------------------------------
# Shared test agents
# ---------------------------------------------------------------------------

class _SingleCallAgent(BaseTPRMAgent):
    """Agent that makes exactly one LLM call per run."""

    name = "SingleCallAgent"

    async def _emit_findings(self, ctx: ExecutionContext) -> list[Finding]:
        text = await self._call_llm(ctx, prompt="single call prompt")
        return [
            Finding(
                agent=self.name,
                category="test",
                severity="low",
                summary=text or "(empty)",
            )
        ]


class _TwoCallAgent(BaseTPRMAgent):
    """Agent that unconditionally makes two LLM calls per run."""

    name = "TwoCallAgent"

    async def _emit_findings(self, ctx: ExecutionContext) -> list[Finding]:
        first = await self._call_llm(ctx, prompt="first call")
        second = await self._call_llm(ctx, prompt="second call")
        return [
            Finding(
                agent=self.name,
                category="test",
                severity="low",
                summary=f"{first} | {second}",
            )
        ]


# ---------------------------------------------------------------------------
# ScriptedLLM.complete() raises ScriptExhaustedError when script is empty
# ---------------------------------------------------------------------------

async def test_scripted_llm_raises_script_exhausted_error_on_empty_script():
    """Arrange: zero-response script.
    Act: call complete() once.
    Assert: ScriptExhaustedError is raised with informative message.
    """
    from orchestra.core.types import Message, MessageRole

    llm = ScriptedLLM([])
    msgs = [Message(role=MessageRole.USER, content="hello")]

    with pytest.raises(ScriptExhaustedError, match="ScriptedLLM exhausted after 0 calls"):
        await llm.complete(msgs)


async def test_scripted_llm_raises_script_exhausted_error_after_responses_consumed():
    """Arrange: one-response script, already consumed.
    Act: call complete() a second time.
    Assert: ScriptExhaustedError is raised on the second call.
    """
    from orchestra.core.types import Message, MessageRole

    llm = ScriptedLLM(["only response"])
    msgs = [Message(role=MessageRole.USER, content="hello")]

    await llm.complete(msgs)  # consumes the one response

    with pytest.raises(ScriptExhaustedError, match="ScriptedLLM exhausted after 1 calls"):
        await llm.complete(msgs)


# ---------------------------------------------------------------------------
# _call_llm propagates ScriptExhaustedError out of BaseTPRMAgent
# ---------------------------------------------------------------------------

async def test_call_llm_propagates_script_exhausted_error_when_script_empty():
    """Arrange: agent with empty-script provider.
    Act: call agent.run() directly (no safe_specialist wrapper).
    Assert: ScriptExhaustedError propagates — BaseTPRMAgent.run() does NOT
    swallow unknown exceptions (only _SafetySuppressed is caught there).
    """
    llm = ScriptedLLM([])
    agent = _SingleCallAgent()
    ctx = ExecutionContext(provider=llm)

    with pytest.raises(ScriptExhaustedError):
        await agent.run(ctx)


# ---------------------------------------------------------------------------
# safe_specialist converts ScriptExhaustedError to critical/agent-error Finding
# ---------------------------------------------------------------------------

async def test_safe_specialist_converts_script_exhausted_error_to_critical_finding():
    """Arrange: empty-script ScriptedLLM; agent that calls _call_llm once.
    Act: invoke wrapped runner from safe_specialist.
    Assert: returns one Finding with severity=critical, category=agent-error,
    and the exception type name in the summary.
    """
    llm = ScriptedLLM([])
    wrapped = safe_specialist(_SingleCallAgent())
    ctx = ExecutionContext(provider=llm)

    findings = await wrapped(ctx)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.agent == "SingleCallAgent"
    assert finding.severity == "critical"
    assert finding.category == "agent-error"
    assert "ScriptExhaustedError" in finding.summary


async def test_safe_specialist_critical_finding_raw_contains_exception_type():
    """Arrange: empty-script ScriptedLLM.
    Act: invoke safe_specialist wrapper.
    Assert: Finding.raw['exception_type'] == 'ScriptExhaustedError'.
    """
    llm = ScriptedLLM([])
    wrapped = safe_specialist(_SingleCallAgent())
    ctx = ExecutionContext(provider=llm)

    findings = await wrapped(ctx)

    assert findings[0].raw.get("exception_type") == "ScriptExhaustedError"


# ---------------------------------------------------------------------------
# _TwoCallAgent with one-response script — exhausted on second call
# ---------------------------------------------------------------------------

async def test_two_call_agent_exhausted_on_second_call_raw_run_raises():
    """Arrange: one-response script; agent requires two calls.
    Act: call agent.run() directly.
    Assert: ScriptExhaustedError is raised (first call succeeds, second exhausts).
    """
    llm = ScriptedLLM(["first response"])
    agent = _TwoCallAgent()
    ctx = ExecutionContext(provider=llm)

    with pytest.raises(ScriptExhaustedError):
        await agent.run(ctx)

    # Confirm first call was made before exhaustion
    assert llm.call_count == 2


async def test_two_call_agent_exhausted_on_second_call_safe_specialist_wraps_to_critical():
    """Arrange: one-response script; agent requires two calls.
    Act: invoke safe_specialist wrapper.
    Assert: returns critical/agent-error Finding, not a crash.
    The first call succeeds; the second triggers ScriptExhaustedError
    which safe_specialist converts.
    """
    llm = ScriptedLLM(["first response"])
    wrapped = safe_specialist(_TwoCallAgent())
    ctx = ExecutionContext(provider=llm)

    findings = await wrapped(ctx)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.agent == "TwoCallAgent"
    assert finding.severity == "critical"
    assert finding.category == "agent-error"
    assert "ScriptExhaustedError" in finding.summary
    assert finding.raw.get("exception_type") == "ScriptExhaustedError"
    # First call succeeded; second triggered exhaustion
    assert llm.call_count == 2


# ---------------------------------------------------------------------------
# assert_all_consumed — early-exit scenario (unconsumed responses remain)
# ---------------------------------------------------------------------------

async def test_assert_all_consumed_raises_when_agent_exits_before_using_all_responses():
    """Arrange: two-response script; agent only makes one call (early exit).
    Act: call assert_all_consumed() after the single-call agent runs.
    Assert: AssertionError is raised and reports the number of unconsumed responses.
    """
    llm = ScriptedLLM(["response one", "response two"])
    agent = _SingleCallAgent()
    ctx = ExecutionContext(provider=llm)

    await agent.run(ctx)  # consumes only the first response

    with pytest.raises(AssertionError, match="1 unconsumed response"):
        llm.assert_all_consumed()


async def test_assert_all_consumed_raises_when_zero_calls_made_against_non_empty_script():
    """Arrange: script with one response; no calls are made at all.
    Act: assert_all_consumed() immediately.
    Assert: AssertionError reports 1 unconsumed response.
    """
    llm = ScriptedLLM(["unused response"])

    with pytest.raises(AssertionError, match="1 unconsumed response"):
        llm.assert_all_consumed()


async def test_assert_all_consumed_error_message_includes_used_and_total_counts():
    """Arrange: three-response script; agent makes one call.
    Act: assert_all_consumed().
    Assert: error message states 'used 1 of 3' (or equivalent count info).
    """
    llm = ScriptedLLM(["r1", "r2", "r3"])
    agent = _SingleCallAgent()
    ctx = ExecutionContext(provider=llm)

    await agent.run(ctx)

    with pytest.raises(AssertionError, match=r"used 1 of 3"):
        llm.assert_all_consumed()


# ---------------------------------------------------------------------------
# assert_all_consumed — exact consumption (happy path)
# ---------------------------------------------------------------------------

async def test_assert_all_consumed_passes_silently_when_all_responses_consumed_exactly():
    """Arrange: one-response script; single-call agent.
    Act: run agent, then assert_all_consumed().
    Assert: no exception raised.
    """
    llm = ScriptedLLM(["exactly right"])
    agent = _SingleCallAgent()
    ctx = ExecutionContext(provider=llm)

    await agent.run(ctx)
    llm.assert_all_consumed()  # must not raise


async def test_assert_all_consumed_passes_silently_for_two_call_agent_with_two_responses():
    """Arrange: two-response script; two-call agent.
    Act: run agent, then assert_all_consumed().
    Assert: no exception raised; call_count == 2.
    """
    llm = ScriptedLLM(["first", "second"])
    agent = _TwoCallAgent()
    ctx = ExecutionContext(provider=llm)

    await agent.run(ctx)

    assert llm.call_count == 2
    llm.assert_all_consumed()  # must not raise


async def test_assert_all_consumed_passes_on_empty_script_with_zero_calls():
    """Arrange: empty script; no calls made.
    Act: assert_all_consumed() on empty script.
    Assert: no exception raised (zero remaining is still valid).
    """
    llm = ScriptedLLM([])
    llm.assert_all_consumed()  # must not raise
