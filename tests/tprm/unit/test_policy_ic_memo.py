"""Unit tests for PolicyAgent IC memo / 4-way classification (Plan 03 / REQ-09)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from orchestra_tprm.agents.policy import (
    PolicyAgent, _ic_to_mitigation, _severity_to_probability,
)
from orchestra_tprm.modes.config import ModeConfig, SpecialistModels
from orchestra_tprm.schemas import Finding, MAScope


class _StubBQ:
    async def append_findings(self, *args, **kwargs) -> int:
        return 0


@pytest.fixture
def policy_agent(tmp_path: Path) -> PolicyAgent:
    pack = tmp_path / "pack.yaml"
    pack.write_text(yaml.safe_dump({
        "weights": {"low": 1, "medium": 3, "high": 5, "critical": 10},
        "verdict": {
            "reject_if_any_critical": True,
            "reject_above": 30,
            "conditional_above": 10,
        },
    }))
    tpl = tmp_path / "tpl.txt"
    tpl.write_text("x")
    cfg = ModeConfig(
        name="ma",
        intake_model="m",
        router_model="m",
        specialists=SpecialistModels(),
        policy_model="m",
        coordinator_model="m",
        coordinator_template=str(tpl),
        policy_pack=str(pack),
        output_kind="doc",
    )
    return PolicyAgent(mode_config=cfg, bq=_StubBQ(), dataset="d", table="t")


async def test_vendor_mode_no_ma_scope_uses_legacy_verdict(policy_agent: PolicyAgent) -> None:
    """Without ma_scope, the legacy YAML-driven verdict is preserved."""
    f = Finding(agent="A", category="c", severity="low", summary="").model_dump()
    out = await policy_agent({"findings": [f]})
    assert out["policy_verdict"] in {"approve", "conditional-approve", "reject"}
    # IC memo is still emitted (neutral placeholder)
    assert out["ic_memo"]["recommendation"] == "proceed"


async def test_deal_stopper_finding_forces_walk(policy_agent: PolicyAgent) -> None:
    """Any ic_decision='deal-stopper' finding triggers recommendation='walk'."""
    f = Finding(
        agent="A",
        category="c",
        severity="critical",
        summary="bad",
        ic_decision="deal-stopper",
    ).model_dump()
    out = await policy_agent({
        "findings": [f],
        "ma_scope": MAScope(materiality_threshold_usd=1000).model_dump(),
    })
    assert out["policy_verdict"] == "walk"
    assert out["ic_memo"]["recommendation"] == "walk"


async def test_exposure_above_materiality_triggers_reprice(policy_agent: PolicyAgent) -> None:
    """Total upper-bound exposure exceeding materiality threshold → reprice."""
    f = Finding(
        agent="A",
        category="c",
        severity="medium",
        summary="x",
        ic_decision="price-adjustment",
        exposure_usd_range=(0, 5_000),
    ).model_dump()
    out = await policy_agent({
        "findings": [f],
        "ma_scope": MAScope(materiality_threshold_usd=1_000).model_dump(),
    })
    assert out["policy_verdict"] == "reprice"


async def test_deal_breaker_keyword_match_forces_walk(policy_agent: PolicyAgent) -> None:
    """A MAScope deal-breaker keyword found in any finding summary → walk."""
    f = Finding(
        agent="A",
        category="c",
        severity="high",
        summary="Going-concern doubt disclosed in 10-K filing.",
    ).model_dump()
    out = await policy_agent({
        "findings": [f],
        "ma_scope": MAScope(deal_breakers=["going-concern"]).model_dump(),
    })
    assert out["policy_verdict"] == "walk"


def test_helper_mappings() -> None:
    """_ic_to_mitigation and _severity_to_probability table values."""
    assert _ic_to_mitigation("deal-stopper") == "CP"
    assert _ic_to_mitigation("price-adjustment") == "price-chip"
    assert _ic_to_mitigation("SPA-protection") == "indemnity"
    assert _ic_to_mitigation("post-close-monitoring") == "post-close"
    assert _ic_to_mitigation(None) == "post-close"
    assert _ic_to_mitigation("unknown-string") == "post-close"

    assert _severity_to_probability("critical") == "high"
    assert _severity_to_probability("high") == "high"
    assert _severity_to_probability("medium") == "medium"
    assert _severity_to_probability("low") == "low"
    assert _severity_to_probability("bogus") == "low"
