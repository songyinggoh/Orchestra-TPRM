"""Unit tests for PolicyAgent.

Uses a ``PolicyFakeBQ`` in-process stub that satisfies ``BigQueryAdapterP``
without any network or database calls. No LLM is needed — PolicyAgent is
pure rule-based logic over Finding objects.
"""
from __future__ import annotations

import pytest

from orchestra.core.context import ExecutionContext
from orchestra_tprm.agents.policy import PolicyAgent
from orchestra_tprm.modes.config import load_mode
from orchestra_tprm.schemas import Citation, Finding


# ---------------------------------------------------------------------------
# Test-local stub: satisfies BigQueryAdapterP without real BQ
# ---------------------------------------------------------------------------

class PolicyFakeBQ:
    """Minimal async BQ stub. Stores all appended rows in ``self.rows``."""

    def __init__(self) -> None:
        self.rows: list[Finding] = []

    async def append_findings(
        self,
        dataset: str,
        table: str,
        run_id: str,
        findings: list[Finding],
    ) -> int:
        self.rows.extend(findings)
        return len(findings)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _ctx() -> ExecutionContext:
    ctx = ExecutionContext()
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_policy_computes_weighted_score_and_verdict():
    """Weighted score = sum of per-severity weights; verdict is data-driven."""
    cfg = load_mode("vendor")
    bq = PolicyFakeBQ()
    agent = PolicyAgent(mode_config=cfg, bq=bq, dataset="ds", table="tbl")
    findings = [
        Finding(agent="LegalAgent", category="liability", severity="high", summary=""),
        Finding(agent="SecurityAgent", category="soc2-cc6.1", severity="critical", summary=""),
    ]
    ctx = _ctx()
    ctx.state = {"findings": findings}
    update = await agent(ctx.state, ctx=ctx)
    # Risk score: high(7) + critical(15) = 22
    assert update["risk_score"] == 22.0
    assert update["policy_verdict"] in {"reject", "conditional-approve", "approve"}
    # Any critical → reject
    assert update["policy_verdict"] == "reject"
    # All findings written to BQ
    assert len(bq.rows) == 2


@pytest.mark.asyncio
async def test_policy_verdict_thresholds():
    """Verdict thresholds: approve / conditional-approve / reject."""
    cfg = load_mode("vendor")

    async def verdict(findings: list[Finding]) -> str:
        bq = PolicyFakeBQ()
        agent = PolicyAgent(mode_config=cfg, bq=bq, dataset="ds", table="tbl")
        ctx = _ctx()
        ctx.state = {"findings": findings}
        u = await agent(ctx.state, ctx=ctx)
        return u["policy_verdict"]

    # No findings → approve (score = 0)
    assert (await verdict([])) == "approve"

    # Single medium (score = 3) → approve
    assert (
        await verdict([Finding(agent="X", category="c", severity="medium", summary="")])
    ) == "approve"

    # 2 highs + 1 medium = 7+7+3 = 17 → conditional-approve
    assert (
        await verdict([
            Finding(agent="X", category="c", severity="high", summary=""),
            Finding(agent="X", category="c", severity="high", summary=""),
            Finding(agent="X", category="c", severity="medium", summary=""),
        ])
    ) == "conditional-approve"

    # 1 critical → reject (reject_if_any_critical rule)
    assert (
        await verdict([Finding(agent="X", category="c", severity="critical", summary="")])
    ) == "reject"


@pytest.mark.asyncio
async def test_policy_reject_above_score_threshold():
    """Score > reject_above (30) triggers reject even without any critical."""
    cfg = load_mode("vendor")
    bq = PolicyFakeBQ()
    agent = PolicyAgent(mode_config=cfg, bq=bq, dataset="ds", table="tbl")
    # 5 high findings = 5 * 7 = 35 > 30, no criticals
    findings = [
        Finding(agent="X", category="c", severity="high", summary="")
        for _ in range(5)
    ]
    ctx = _ctx()
    ctx.state = {"findings": findings}
    update = await agent(ctx.state, ctx=ctx)
    assert update["risk_score"] == 35.0
    assert update["policy_verdict"] == "reject"
    assert len(bq.rows) == 5


@pytest.mark.asyncio
async def test_policy_empty_findings_writes_zero_rows():
    """Empty findings list → approve, nothing written to BQ."""
    cfg = load_mode("vendor")
    bq = PolicyFakeBQ()
    agent = PolicyAgent(mode_config=cfg, bq=bq, dataset="ds", table="tbl")
    ctx = _ctx()
    ctx.state = {"findings": []}
    update = await agent(ctx.state, ctx=ctx)
    assert update["risk_score"] == 0.0
    assert update["policy_verdict"] == "approve"
    assert len(bq.rows) == 0


@pytest.mark.asyncio
async def test_policy_coerces_dict_findings():
    """Findings passed as plain dicts (graph deserialisation) are coerced."""
    cfg = load_mode("vendor")
    bq = PolicyFakeBQ()
    agent = PolicyAgent(mode_config=cfg, bq=bq, dataset="ds", table="tbl")
    findings_as_dicts = [
        {"agent": "A", "category": "risk", "severity": "low", "summary": "minor issue"},
    ]
    ctx = _ctx()
    ctx.state = {"findings": findings_as_dicts}
    update = await agent(ctx.state, ctx=ctx)
    # low weight = 1 → approve
    assert update["risk_score"] == 1.0
    assert update["policy_verdict"] == "approve"
    assert isinstance(bq.rows[0], Finding)


@pytest.mark.asyncio
async def test_policy_no_mode_literals():
    """Invariant: PolicyAgent source must not branch on mode name literals."""
    import inspect
    from orchestra_tprm.agents import policy as policy_mod
    src = inspect.getsource(policy_mod)
    # Strip comments and docstrings by only scanning executable-looking lines
    code_lines = [
        line for line in src.splitlines()
        if not line.lstrip().startswith(("#", '"""', "'''"))
    ]
    code = "\n".join(code_lines)
    assert 'if mode ==' not in code, (
        "PolicyAgent violates no-mode-literal invariant: 'if mode ==' found in code"
    )
    # Mode names must not appear as string comparisons
    for mode in ('== "vendor"', "== 'vendor'", '== "ma"', "== 'ma'"):
        assert mode not in code, (
            f"PolicyAgent violates data-driven invariant: {mode!r} found in code"
        )


@pytest.mark.asyncio
async def test_policy_loads_policy_pack_from_mode_config():
    """PolicyAgent reads policy_pack path from ModeConfig, not a hardcoded path."""
    cfg = load_mode("vendor")
    bq = PolicyFakeBQ()
    agent = PolicyAgent(mode_config=cfg, bq=bq, dataset="ds", table="tbl")
    # The loaded policy must have the weights key defined in vendor.yaml
    assert "weights" in agent._policy
    assert agent._policy["weights"]["critical"] == 15


@pytest.mark.asyncio
async def test_policy_verdict_with_evidence():
    """Findings carrying Citation evidence are handled correctly."""
    cfg = load_mode("vendor")
    bq = PolicyFakeBQ()
    agent = PolicyAgent(mode_config=cfg, bq=bq, dataset="ds", table="tbl")
    findings = [
        Finding(
            agent="LegalAgent",
            category="liability",
            severity="high",
            summary="Liability cap is 1x annual fees.",
            evidence=[Citation(file_id="msa.pdf", page=12, snippet="cap is limited...")],
        ),
    ]
    ctx = _ctx()
    ctx.state = {"findings": findings}
    update = await agent(ctx.state, ctx=ctx)
    # high(7) = 7 ≤ 10 → approve
    assert update["policy_verdict"] == "approve"
    assert update["risk_score"] == 7.0
    # Evidence preserved on the Finding object in BQ rows
    assert len(bq.rows[0].evidence) == 1
