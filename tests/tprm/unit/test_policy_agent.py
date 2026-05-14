"""Unit tests for PolicyAgent (policy_node).

Uses asyncio_mode = "auto" — no @pytest.mark.asyncio decorators needed.
"""
from __future__ import annotations

from pathlib import Path

from orchestra_tprm.agents.policy import policy_node
from orchestra_tprm.schemas import Finding

# Resolve policy YAML paths relative to this file's location.
# tests/tprm/unit/test_policy_agent.py  →  src/orchestra_tprm/policies/
_REPO_ROOT = Path(__file__).parent.parent.parent.parent
VENDOR_POLICY = str(_REPO_ROOT / "src/orchestra_tprm/policies/vendor.yaml")
MA_POLICY = str(_REPO_ROOT / "src/orchestra_tprm/policies/ma.yaml")


def _finding(severity: str) -> Finding:
    return Finding(
        agent="TestAgent",
        category="test",
        severity=severity,  # type: ignore[arg-type]
        summary="test finding",
    )


# ---------------------------------------------------------------------------
# Vendor policy tests
# ---------------------------------------------------------------------------


async def test_vendor_no_findings_returns_approve():
    result = await policy_node({"findings": []}, VENDOR_POLICY)
    assert result["policy_verdict"] == "approve"
    assert result["risk_score"] == 0.0


async def test_vendor_critical_finding_blocks():
    result = await policy_node(
        {"findings": [_finding("critical")]}, VENDOR_POLICY
    )
    assert result["policy_verdict"] == "block"


async def test_vendor_two_high_findings_conditional():
    result = await policy_node(
        {"findings": [_finding("high"), _finding("high")]}, VENDOR_POLICY
    )
    assert result["policy_verdict"] == "conditional"


async def test_vendor_one_high_finding_approves():
    result = await policy_node(
        {"findings": [_finding("high")]}, VENDOR_POLICY
    )
    assert result["policy_verdict"] == "approve"


# ---------------------------------------------------------------------------
# M&A policy tests
# ---------------------------------------------------------------------------


async def test_ma_no_findings_returns_conditional():
    """M&A default catch-all is 'conditional', not 'approve'."""
    result = await policy_node({"findings": []}, MA_POLICY)
    assert result["policy_verdict"] == "conditional"
    assert result["risk_score"] == 0.0


async def test_ma_critical_finding_blocks():
    result = await policy_node(
        {"findings": [_finding("critical")]}, MA_POLICY
    )
    assert result["policy_verdict"] == "block"


async def test_ma_three_high_findings_blocks():
    result = await policy_node(
        {"findings": [_finding("high"), _finding("high"), _finding("high")]},
        MA_POLICY,
    )
    assert result["policy_verdict"] == "block"


async def test_ma_one_high_finding_conditional():
    result = await policy_node(
        {"findings": [_finding("high")]}, MA_POLICY
    )
    assert result["policy_verdict"] == "conditional"


# ---------------------------------------------------------------------------
# Risk score arithmetic
# ---------------------------------------------------------------------------


async def test_risk_score_weights_sum_correctly():
    """Vendor: 2 × medium (3) + 1 × high (7) = 13.0"""
    findings = [_finding("medium"), _finding("medium"), _finding("high")]
    result = await policy_node({"findings": findings}, VENDOR_POLICY)
    assert result["risk_score"] == 13.0


async def test_risk_score_capped_at_100():
    """Many CRITICAL findings should cap at 100.0, not overflow."""
    findings = [_finding("critical")] * 20  # 20 × 20 = 400 raw
    result = await policy_node({"findings": findings}, VENDOR_POLICY)
    assert result["risk_score"] == 100.0


# ---------------------------------------------------------------------------
# Dict-based findings (raw dicts, not Finding objects)
# ---------------------------------------------------------------------------


async def test_findings_as_dicts_work():
    """state["findings"] may contain plain dicts — policy_node must handle both."""
    findings = [
        {"severity": "critical", "category": "test", "summary": "dict finding"},
    ]
    result = await policy_node({"findings": findings}, VENDOR_POLICY)
    assert result["policy_verdict"] == "block"
    assert result["risk_score"] == 20.0
