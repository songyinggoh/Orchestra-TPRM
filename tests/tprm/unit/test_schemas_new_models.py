"""Unit tests for the new Pydantic models added for the 3-agent delta."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestra_tprm.schemas import (
    Finding,
    RemediationItem,
    RemediationPlan,
    RiskDriver,
    RiskScore,
)


def test_risk_driver_round_trip() -> None:
    d = RiskDriver(
        dimension="security",
        finding_id="abc123",
        severity="high",
        one_liner="SOC2 CC6.1 evidence missing.",
    )
    assert d.model_dump()["dimension"] == "security"
    assert d.severity == "high"


def test_risk_score_clamps_verdict_literal() -> None:
    r = RiskScore(
        overall=42,
        verdict="amber",
        dimensions={"security": 60, "legal": 20},
        top_risk_drivers=[],
        explanation="Mixed risk.",
    )
    assert r.overall == 42
    assert r.verdict == "amber"

    with pytest.raises(ValidationError):
        RiskScore(
            overall=42, verdict="bogus", dimensions={}, top_risk_drivers=[], explanation=""
        )


def test_risk_score_clamps_overall_to_0_100() -> None:
    with pytest.raises(ValidationError):
        RiskScore(overall=101, verdict="red", dimensions={}, top_risk_drivers=[], explanation="")

    with pytest.raises(ValidationError):
        RiskScore(overall=-1, verdict="green", dimensions={}, top_risk_drivers=[], explanation="")


def test_remediation_item_priority_validates() -> None:
    item = RemediationItem(
        finding_id="abc",
        action="Demand SOC2 Type II report",
        owner="vendor",
        priority="P0",
        leverage="MSA section 14.2 - security warranty",
    )
    assert item.priority == "P0"

    with pytest.raises(ValidationError):
        RemediationItem(
            finding_id="x",
            action="x",
            owner="vendor",
            priority="P9",
            leverage="x",
        )


def test_remediation_plan_defaults_horizon_zero() -> None:
    plan = RemediationPlan(items=[], horizon_days=0, summary="No remediation required.")
    assert plan.horizon_days == 0
    assert plan.items == []


def test_finding_id_factory_unique_uuid4() -> None:
    a = Finding(agent="legal", category="x", severity="low", summary="a")
    b = Finding(agent="legal", category="x", severity="low", summary="b")
    assert a.id != b.id
    # uuid4 with dashes = 36 chars
    assert len(a.id) == 36
    assert a.id.count("-") == 4
