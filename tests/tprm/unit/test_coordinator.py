"""Unit tests for Coordinator (Task 23).

The Coordinator is mode-agnostic: behaviour is dispatched via
``ModeConfig.output_kind`` (``"sheet"`` for vendor, ``"doc"`` for M&A) and
the template path is loaded from ``ModeConfig.coordinator_template``. No
string-literal mode branching may appear in the runtime decision path.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from orchestra.core.context import ExecutionContext
from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM
from orchestra_tprm.adapters.docs import FakeDocsAdapter
from orchestra_tprm.adapters.sheets import FakeSheetsAdapter
from orchestra_tprm.agents.coordinator import Coordinator
from orchestra_tprm.modes.config import load_mode
from orchestra_tprm.schemas import Citation, Finding, ICMemo, ICRiskItem, PMIItem, PMIPlan


@pytest.mark.asyncio
async def test_vendor_coordinator_writes_sheet_and_local_csv(tmp_path: Path) -> None:
    """Vendor mode appends a row to the Sheets adapter AND mirrors the sheet
    to a local CSV under ``local_dir``."""
    cfg = load_mode("vendor")
    sheets = FakeSheetsAdapter()
    coord = Coordinator(
        mode_config=cfg,
        sheets=sheets,
        sheet_id="SHEET-FAKE",
        local_dir=tmp_path,
    )
    findings = [
        Finding(
            agent="LegalAgent",
            category="liability",
            severity="high",
            summary="Liability cap is 1x annual fees.",
            evidence=[Citation(file_id="msa.pdf", page=12, snippet="cap...")],
        )
    ]
    state = {
        "subject_name": "Acme",
        "findings": findings,
        "policy_verdict": "conditional-approve",
        "risk_score": 7.0,
    }
    ctx = ExecutionContext(
        provider=ScriptedLLM(
            [
                LLMResponse(
                    content=(
                        "Recommendation: conditional approve. "
                        "Renegotiate liability cap to 12 months."
                    )
                )
            ]
        )
    )
    update = await coord(state, ctx=ctx)

    # Sheet row written
    rows = sheets.read_rows("SHEET-FAKE")
    assert len(rows) == 1
    assert "liability" in rows[0]["categories"]
    assert rows[0]["policy_verdict"] == "conditional-approve"

    # verdict_doc_id is the sheet_id; verdict_local_path is a file:// URL to CSV
    assert update["verdict_doc_id"] == "SHEET-FAKE"
    assert update["verdict_local_path"].startswith("file://")
    csv_path = Path(update["verdict_local_path"].removeprefix("file://"))
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "liability" in csv_text
    assert "conditional-approve" in csv_text


@pytest.mark.asyncio
async def test_ma_coordinator_creates_doc_with_sections(tmp_path: Path) -> None:
    """M&A mode creates a doc via FakeDocsAdapter with the locked 6-section order.

    The new _write_doc builds a deterministic sections dict from structured
    state data (ic_memo, pmi_plan, findings). The LLM narrative supplies the
    Executive Summary only; old free-text headings like 'Strategic Fit' are
    no longer part of the output (replaced by structured workstream reports).
    """
    cfg = load_mode("ma")
    docs = FakeDocsAdapter()
    coord = Coordinator(
        mode_config=cfg,
        docs=docs,
        doc_id="",
        local_dir=tmp_path,
    )
    findings = [
        Finding(
            agent="LegalAgent",
            category="change-of-control",
            severity="medium",
            summary="Change-of-control triggers acceleration of executive equity.",
            workstream="legal",
            ic_decision="SPA-protection",
        )
    ]
    ic = ICMemo(
        executive_summary="Conditional approve.",
        headline_terms="SPA protection required for equity acceleration clause.",
        recommendation="proceed",
        risk_register=[
            ICRiskItem(
                finding_id="f1",
                workstream="legal",
                exposure_usd_range=(0, 2_000_000),
                mitigation="indemnity",
                probability="medium",
            )
        ],
    )
    pmi = PMIPlan(
        summary="100-day integration roadmap.",
        items=[
            PMIItem(
                workstream="legal",
                action="Resolve equity acceleration clause",
                deadline_tier="day-30",
                owner="General Counsel",
            )
        ],
    )
    state = {
        "subject_name": "HashiCorp",
        "findings": findings,
        "policy_verdict": "conditional-approve",
        "risk_score": 5.0,
        "ic_memo": ic.model_dump(),
        "pmi_plan": pmi.model_dump(),
    }
    # LLM returns a plain narrative for the Executive Summary
    narrative = "Conditional approve — BSL license risk manageable via SPA."
    ctx = ExecutionContext(provider=ScriptedLLM([LLMResponse(content=narrative)]))
    update = await coord(state, ctx=ctx)

    assert update["verdict_doc_id"], "Coordinator must populate verdict_doc_id"
    assert docs._docs, "FakeDocsAdapter received no create_doc call"
    body = "\n".join(next(iter(docs._docs.values())))
    # Verify all 6 locked sections appear in the output body
    for heading in (
        "Executive Summary",
        "IC Memo",
        "Workstream Reports",
        "Risk Register",
        "PMI 100-Day Plan",
        "Appendix: Full Findings",
    ):
        assert heading in body, f"Section {heading!r} missing from deal memo body"
    # Verify structured content rendered correctly
    assert "PROCEED" in body, "IC recommendation should be uppercased in IC Memo section"
    assert "DAY-30" in body, "PMI tier heading should appear in PMI section"
    assert "indemnity" in body, "Risk register mitigation should appear"


@pytest.mark.asyncio
async def test_coordinator_loads_template_by_name_only(tmp_path: Path) -> None:
    """Invariant (d): Coordinator's behaviour is loaded by NAME from mode
    config, not by ``if mode == ...`` literals. The ``_template_path``
    attribute must equal ``cfg.coordinator_template``."""
    cfg = load_mode("vendor")
    coord = Coordinator(
        mode_config=cfg,
        sheets=FakeSheetsAdapter(),
        sheet_id="x",
        local_dir=tmp_path,
    )
    assert coord._template_path == cfg.coordinator_template


@pytest.mark.asyncio
async def test_coordinator_no_mode_literals_in_source() -> None:
    """Invariant (b): ``if mode ==`` must not appear in the Coordinator source."""
    import inspect

    from orchestra_tprm.agents import coordinator as coord_mod

    src = inspect.getsource(coord_mod)
    code_lines = [
        line for line in src.splitlines()
        if not line.lstrip().startswith(("#", '"""', "'''"))
    ]
    code = "\n".join(code_lines)
    assert "if mode ==" not in code, (
        "Coordinator violates the no-mode-literal invariant"
    )
