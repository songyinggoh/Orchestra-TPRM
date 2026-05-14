"""Concurrency tests for safe_specialist parallel fan-out.

Covers:
  - Three safe_specialist-wrapped agents via asyncio.gather → all findings
    collected, no interleaving or data loss.
  - One agent raises a generic exception while two succeed → exception agent
    returns critical/agent-error Finding; others return normal findings.
  - One agent raises _SafetySuppressed (propagated from run()) while others
    succeed → safety agent returns filter-suppressed Finding; others normal.
  - All three agents fail → three critical/agent-error Findings, one per
    agent, with correct agent names.
  - Concurrent agents share NO mutable state: each gets its own
    ExecutionContext backed by its own ScriptedLLM.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from orchestra.core.context import ExecutionContext
from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM
from orchestra_tprm.agents.base import (
    BaseTPRMAgent,
    _SafetySuppressed,
    safe_specialist,
)
from orchestra_tprm.schemas import Finding

# ---------------------------------------------------------------------------
# Helpers / mini-specialist factories
# ---------------------------------------------------------------------------


def _make_ctx(llm: ScriptedLLM) -> ExecutionContext:
    """Return a fresh ExecutionContext backed by the given ScriptedLLM."""
    return ExecutionContext(provider=llm)


def _scripted_agent(name: str, responses: list[LLMResponse | str]) -> tuple[Any, ScriptedLLM]:
    """Return (safe_specialist_callable, ScriptedLLM) for a well-behaved agent
    that calls the LLM once and emits one Finding per response."""

    llm = ScriptedLLM(responses)

    # Capture agent_name in closure to avoid late-binding issues with `name`
    agent_name = name

    async def _emit_findings(self, ctx: ExecutionContext) -> list[Finding]:
        text = await self._call_llm(ctx, prompt=f"{agent_name}: analyze this")
        return [
            Finding(
                agent=self.name,
                category="ok",
                severity="low",
                summary=text,
            )
        ]

    agent_cls = type(
        agent_name,
        (BaseTPRMAgent,),
        {
            "name": agent_name,
            "_emit_findings": _emit_findings,
        },
    )
    agent = agent_cls()
    wrapped = safe_specialist(agent)
    return wrapped, llm


def _boom_agent(name: str, exc: Exception) -> Any:
    """Return a safe_specialist-wrapped agent whose _emit_findings raises exc."""
    agent_cls = type(
        name,
        (BaseTPRMAgent,),
        {
            "name": name,
            "_emit_findings": lambda self, ctx: _raise(exc),
        },
    )
    agent = agent_cls()
    return safe_specialist(agent)


async def _raise(exc: Exception) -> None:  # noqa: RUF029
    raise exc


def _safety_suppressed_agent(name: str) -> Any:
    """Return a safe_specialist-wrapped agent whose run() propagates
    _SafetySuppressed.

    To reach safe_specialist's own _SafetySuppressed handler, the exception
    must escape agent.run().  BaseTPRMAgent.run() catches _SafetySuppressed
    raised from _emit_findings; so we override run() directly to raise it,
    bypassing the base class handler.
    """

    async def _run(self, ctx: ExecutionContext) -> list[Finding]:
        raise _SafetySuppressed()

    async def _emit_findings(self, ctx: ExecutionContext) -> list[Finding]:
        raise NotImplementedError("should not be reached — run() is overridden")

    agent_cls = type(
        name,
        (BaseTPRMAgent,),
        {
            "name": name,
            "run": _run,
            "_emit_findings": _emit_findings,
        },
    )
    agent = agent_cls()
    return safe_specialist(agent)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_safe_specialist_three_agents_gather_collects_all_findings():
    """Three concurrent safe_specialists via asyncio.gather return all
    findings with no interleaving or data loss."""
    # Arrange — three independent agents, each with their own LLM + ctx
    alpha_wrapped, alpha_llm = _scripted_agent("AlphaAgent", ["alpha-result"])
    beta_wrapped, beta_llm = _scripted_agent("BetaAgent", ["beta-result"])
    gamma_wrapped, gamma_llm = _scripted_agent("GammaAgent", ["gamma-result"])

    alpha_ctx = _make_ctx(alpha_llm)
    beta_ctx = _make_ctx(beta_llm)
    gamma_ctx = _make_ctx(gamma_llm)

    # Act — true concurrent fan-out
    results: list[list[Finding]] = await asyncio.gather(
        alpha_wrapped(alpha_ctx),
        beta_wrapped(beta_ctx),
        gamma_wrapped(gamma_ctx),
    )

    # Assert — flatten: three findings total, one per agent
    all_findings = [f for batch in results for f in batch]
    assert len(all_findings) == 3, (
        f"Expected 3 findings from three agents, got {len(all_findings)}"
    )

    summaries = {f.summary for f in all_findings}
    assert summaries == {"alpha-result", "beta-result", "gamma-result"}, (
        f"Unexpected summaries: {summaries}"
    )

    agent_names = {f.agent for f in all_findings}
    assert agent_names == {"AlphaAgent", "BetaAgent", "GammaAgent"}, (
        f"Unexpected agent names: {agent_names}"
    )


async def test_safe_specialist_one_exception_one_error_finding_two_normal():
    """One failing agent produces critical/agent-error; the two succeeding
    agents produce their normal findings. asyncio.gather does not raise."""
    # Arrange
    ok1_wrapped, ok1_llm = _scripted_agent("OkAgent1", ["result-one"])
    ok2_wrapped, ok2_llm = _scripted_agent("OkAgent2", ["result-two"])
    boom_wrapped = _boom_agent("BoomAgent", RuntimeError("disk full"))

    ok1_ctx = _make_ctx(ok1_llm)
    ok2_ctx = _make_ctx(ok2_llm)
    boom_ctx = _make_ctx(ScriptedLLM([]))

    # Act
    results = await asyncio.gather(
        ok1_wrapped(ok1_ctx),
        ok2_wrapped(ok2_ctx),
        boom_wrapped(boom_ctx),
    )

    # Assert — no gather-level exception raised (safe_specialist swallows it)
    ok1_batch, ok2_batch, boom_batch = results

    assert len(ok1_batch) == 1
    assert ok1_batch[0].category == "ok"
    assert ok1_batch[0].summary == "result-one"

    assert len(ok2_batch) == 1
    assert ok2_batch[0].category == "ok"
    assert ok2_batch[0].summary == "result-two"

    assert len(boom_batch) == 1
    boom_finding = boom_batch[0]
    assert boom_finding.agent == "BoomAgent", (
        f"Error finding must carry agent name 'BoomAgent', got {boom_finding.agent!r}"
    )
    assert boom_finding.category == "agent-error", (
        f"Expected category 'agent-error', got {boom_finding.category!r}"
    )
    assert boom_finding.severity == "critical", (
        f"Expected severity 'critical', got {boom_finding.severity!r}"
    )
    assert "disk full" in boom_finding.summary, (
        f"Exception message must appear in summary; got {boom_finding.summary!r}"
    )


async def test_safe_specialist_safety_suppressed_agent_returns_filter_suppressed_finding():
    """Agent whose run() raises _SafetySuppressed gets a filter-suppressed
    Finding; the two other agents complete normally."""
    # Arrange
    ok1_wrapped, ok1_llm = _scripted_agent("OkAgent1", ["clean-result"])
    ok2_wrapped, ok2_llm = _scripted_agent("OkAgent2", ["other-result"])
    safety_wrapped = _safety_suppressed_agent("SafetyAgent")

    ok1_ctx = _make_ctx(ok1_llm)
    ok2_ctx = _make_ctx(ok2_llm)
    safety_ctx = _make_ctx(ScriptedLLM([]))

    # Act
    results = await asyncio.gather(
        ok1_wrapped(ok1_ctx),
        safety_wrapped(safety_ctx),
        ok2_wrapped(ok2_ctx),
    )

    ok1_batch, safety_batch, ok2_batch = results

    # Assert — normal agents unaffected
    assert len(ok1_batch) == 1 and ok1_batch[0].category == "ok"
    assert len(ok2_batch) == 1 and ok2_batch[0].category == "ok"

    # Safety agent produces exactly one filter-suppressed Finding
    assert len(safety_batch) == 1, (
        f"Expected 1 filter-suppressed Finding, got {len(safety_batch)}"
    )
    safety_finding = safety_batch[0]
    assert safety_finding.agent == "SafetyAgent", (
        f"filter-suppressed Finding must carry agent name; got {safety_finding.agent!r}"
    )
    assert safety_finding.category == "filter-suppressed", (
        f"Expected category 'filter-suppressed', got {safety_finding.category!r}"
    )
    assert safety_finding.severity == "medium", (
        f"Expected severity 'medium', got {safety_finding.severity!r}"
    )


async def test_safe_specialist_all_three_fail_returns_three_critical_findings():
    """When every agent in the gather fails, all three agent-error Findings
    are returned and each carries the correct agent name."""
    # Arrange — three distinct exception types to confirm names are not mixed
    alpha_wrapped = _boom_agent("AlphaFail", ValueError("alpha-bad"))
    beta_wrapped = _boom_agent("BetaFail", KeyError("beta-bad"))
    gamma_wrapped = _boom_agent("GammaFail", RuntimeError("gamma-bad"))

    alpha_ctx = _make_ctx(ScriptedLLM([]))
    beta_ctx = _make_ctx(ScriptedLLM([]))
    gamma_ctx = _make_ctx(ScriptedLLM([]))

    # Act
    results = await asyncio.gather(
        alpha_wrapped(alpha_ctx),
        beta_wrapped(beta_ctx),
        gamma_wrapped(gamma_ctx),
    )

    # Assert — three batches, each with exactly one critical/agent-error Finding
    assert len(results) == 3, f"gather must return 3 result batches, got {len(results)}"

    for batch in results:
        assert len(batch) == 1, f"Each failing agent produces exactly 1 Finding; got {batch}"
        finding = batch[0]
        assert finding.category == "agent-error"
        assert finding.severity == "critical"

    # Names must match agent identity — not swapped
    names = {batch[0].agent for batch in results}
    assert names == {"AlphaFail", "BetaFail", "GammaFail"}, (
        f"agent names in error Findings are wrong or swapped: {names}"
    )

    # Error message content must belong to the right agent
    by_name = {batch[0].agent: batch[0] for batch in results}
    assert "alpha-bad" in by_name["AlphaFail"].summary
    assert "beta-bad" in by_name["BetaFail"].summary
    assert "gamma-bad" in by_name["GammaFail"].summary


async def test_safe_specialist_concurrent_agents_have_isolated_mutable_state():
    """Each concurrent agent must observe only its own LLM call log — no
    shared ScriptedLLM state bleeds between agents."""
    # Arrange — three agents with distinct scripted responses, each with its
    # own ScriptedLLM so call_count is agent-local.
    alpha_wrapped, alpha_llm = _scripted_agent("AlphaIsolated", ["alpha-only"])
    beta_wrapped, beta_llm = _scripted_agent("BetaIsolated", ["beta-only"])
    gamma_wrapped, gamma_llm = _scripted_agent("GammaIsolated", ["gamma-only"])

    alpha_ctx = _make_ctx(alpha_llm)
    beta_ctx = _make_ctx(beta_llm)
    gamma_ctx = _make_ctx(gamma_llm)

    # Act
    await asyncio.gather(
        alpha_wrapped(alpha_ctx),
        beta_wrapped(beta_ctx),
        gamma_wrapped(gamma_ctx),
    )

    # Assert — each LLM received exactly the calls from its own agent
    assert alpha_llm.call_count == 1, (
        f"AlphaIsolated's LLM should see 1 call, got {alpha_llm.call_count}"
    )
    assert beta_llm.call_count == 1, (
        f"BetaIsolated's LLM should see 1 call, got {beta_llm.call_count}"
    )
    assert gamma_llm.call_count == 1, (
        f"GammaIsolated's LLM should see 1 call, got {gamma_llm.call_count}"
    )

    # Each LLM's call log contains only prompts from its own agent
    alpha_prompt = alpha_llm.call_log[0]["messages"][-1].content
    assert "AlphaIsolated" in alpha_prompt, (
        f"Alpha LLM received a prompt not from AlphaIsolated: {alpha_prompt!r}"
    )

    beta_prompt = beta_llm.call_log[0]["messages"][-1].content
    assert "BetaIsolated" in beta_prompt, (
        f"Beta LLM received a prompt not from BetaIsolated: {beta_prompt!r}"
    )

    gamma_prompt = gamma_llm.call_log[0]["messages"][-1].content
    assert "GammaIsolated" in gamma_prompt, (
        f"Gamma LLM received a prompt not from GammaIsolated: {gamma_prompt!r}"
    )
