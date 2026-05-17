"""Unit tests for Coordinator._write_doc M&A section ordering (Plan 07 / REQ-15)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from orchestra_tprm.agents.coordinator import (
    Coordinator,
    _coerce_ic_memo,
    _coerce_pmi_plan,
    _PMI_TIER_ORDER,
    _render_pmi_plan,
    _render_risk_register,
    _render_workstream_section,
)
from orchestra_tprm.modes.config import ModeConfig, SpecialistModels
from orchestra_tprm.schemas import (
    Finding, ICMemo, ICRiskItem, PMIItem, PMIPlan,
)


class _FakeDocs:
    def __init__(self) -> None:
        self.captured: dict[str, str] | None = None

    def populate_ma_memo(self, doc_id: str, sections: dict[str, str]) -> None:
        self.captured = sections

    def create_doc(self, title: str, body: str) -> str:
        return "doc-new"


@pytest.fixture
def coordinator(tmp_path: Path) -> tuple[Coordinator, _FakeDocs]:
    pack = tmp_path / "p.yaml"
    pack.write_text(yaml.safe_dump({}))
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
    fd = _FakeDocs()
    coord = Coordinator(mode_config=cfg, docs=fd, doc_id="existing-doc")
    return coord, fd


async def test_sections_rendered_in_locked_order(coordinator) -> None:
    coord, fd = coordinator

    findings = [
        Finding(agent="A", category="liability-cap", severity="high", summary="Cap is 1x",
                workstream="legal", ic_decision="SPA-protection",
                exposure_usd_range=(0, 500_000)),
        Finding(agent="A", category="gpl", severity="critical", summary="GPL detected",
                workstream="tech", ic_decision="deal-stopper"),
    ]
    ic_memo = ICMemo(
        executive_summary="Exec summary text",
        headline_terms="WALK — GPL contamination unrecoverable",
        recommendation="walk",
        risk_register=[
            ICRiskItem(finding_id="f1", workstream="legal",
                       exposure_usd_range=(0, 500_000),
                       mitigation="indemnity", probability="medium"),
        ],
    )
    pmi_plan = PMIPlan(
        summary="100-day plan",
        items=[
            PMIItem(workstream="tech", action="Replace GPL", deadline_tier="day-30", owner="CIO"),
            PMIItem(workstream="hr", action="Retention", deadline_tier="day-60", owner="CHRO"),
        ],
    )

    state: dict[str, Any] = {
        "subject_name": "TargetCorp",
        "ic_memo": ic_memo.model_dump(),
        "pmi_plan": pmi_plan.model_dump(),
    }

    await coord._write_doc(state, findings, "Executive summary placeholder.")

    assert fd.captured is not None
    keys = list(fd.captured.keys())
    assert keys == [
        "Executive Summary",
        "IC Memo",
        "Workstream Reports",
        "Risk Register",
        "PMI 100-Day Plan",
        "Appendix: Full Findings",
    ]


async def test_workstream_reports_grouped_alphabetically(coordinator) -> None:
    coord, fd = coordinator

    findings = [
        Finding(agent="A", category="x", severity="low", summary="", workstream="tech"),
        Finding(agent="A", category="x", severity="low", summary="", workstream="financial"),
        Finding(agent="A", category="x", severity="low", summary="", workstream="legal"),
    ]
    await coord._write_doc({"subject_name": "X"}, findings, "narr")
    block = fd.captured["Workstream Reports"]
    # All three workstream titles appear (capitalised in the helper)
    assert "Workstream: Financial" in block
    assert "Workstream: Legal" in block
    assert "Workstream: Tech" in block
    # Order: alphabetical → Financial appears before Legal appears before Tech
    idx_fin = block.index("Workstream: Financial")
    idx_legal = block.index("Workstream: Legal")
    idx_tech = block.index("Workstream: Tech")
    assert idx_fin < idx_legal < idx_tech


async def test_pmi_section_uses_canonical_tier_order(coordinator) -> None:
    coord, fd = coordinator

    # Plan with items in shuffled tier order
    pmi_plan = PMIPlan(
        summary="",
        items=[
            PMIItem(workstream="financial", action="C", deadline_tier="day-100", owner="CFO"),
            PMIItem(workstream="tech", action="A", deadline_tier="day-30", owner="CIO"),
            PMIItem(workstream="esg", action="D", deadline_tier="day-180", owner="CSO"),
            PMIItem(workstream="hr", action="B", deadline_tier="day-60", owner="CHRO"),
        ],
    )
    await coord._write_doc(
        {"subject_name": "X", "pmi_plan": pmi_plan.model_dump()},
        [],
        "narr",
    )
    block = fd.captured["PMI 100-Day Plan"]
    idx_30 = block.index("DAY-30")
    idx_60 = block.index("DAY-60")
    idx_100 = block.index("DAY-100")
    idx_180 = block.index("DAY-180")
    assert idx_30 < idx_60 < idx_100 < idx_180


def test_helper_renderers_handle_empty_inputs() -> None:
    """Render helpers should not crash on None / empty inputs."""
    assert _render_risk_register(None) == "No risks registered."
    assert _render_pmi_plan(None) == "No PMI actions planned."
    assert _coerce_ic_memo(None) is None
    assert _coerce_pmi_plan(None) is None
    # Pydantic ignores unknown fields: {"bogus": "data"} coerces to ICMemo with defaults
    coerced = _coerce_ic_memo({"bogus": "data"})
    assert coerced is not None
    assert coerced.recommendation == "proceed"  # default value
    # Workstream renderer with empty findings list
    out = _render_workstream_section("legal", [])
    assert "Workstream: Legal" in out
    assert _PMI_TIER_ORDER == ("day-30", "day-60", "day-100", "day-180")
