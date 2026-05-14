"""M&A mode end-to-end integration tests.

These tests encode the CONTRACT for Tasks 14–40: once the coordinator, policy
agent, specialists (including FinancialAgent), and `build_graph()` factory
support `mode="ma"`, the pipeline must complete on the HashiCorp synthetic
packet and produce a deal-memo via `FakeDocsAdapter`.

Current state — orchestra_tprm.graph does not exist:
    `pytest.importorskip("orchestra_tprm.graph")` causes a clean SKIP at
    collection. Tests will FAIL on assertions once the module lands and
    GREEN when the contract is fulfilled.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM
from orchestra_tprm.adapters import (
    FakeBigQueryAdapter,
    FakeDocsAdapter,
    FakeSheetsAdapter,
    GeminiFilesAdapter,
)

# Skip the entire module cleanly until the graph factory lands.
graph_module = pytest.importorskip(
    "orchestra_tprm.graph",
    reason="orchestra_tprm.graph not yet implemented (Tasks 14–40).",
)


# ---------------------------------------------------------------------------
# Happy path — writes deal memo to a Google Doc
# ---------------------------------------------------------------------------

async def test_ma_mode_happy_path_writes_to_doc(
    seeded_drive_ma,
    scripted_llm_ma_happy_path: ScriptedLLM,
    ma_mode_config: Any,
    run_graph_runner,
):
    """M&A flow on HashiCorp packet — Coordinator must create a Doc and
    append the deal-memo body via `FakeDocsAdapter.create_doc` /
    `append_text`."""
    # Arrange
    build_graph = graph_module.build_graph
    Adapters = graph_module.Adapters
    docs = FakeDocsAdapter()
    sheets = FakeSheetsAdapter()  # unused in M&A but Adapters requires the slot
    bq = FakeBigQueryAdapter()
    adapters = Adapters(
        drive=seeded_drive_ma,
        files=GeminiFilesAdapter(),
        sheets=None,
        docs=docs,
        bq=bq,
        github=None,
    )
    graph = build_graph(
        ma_mode_config,
        adapters=adapters,
        drive_folder_id="HASHICORP_FOLDER",
        sheet_id="",
        doc_id="",  # empty → Coordinator should create_doc(...)
        bq_dataset="orchestra_tprm",
        bq_table="findings_audit",
        github_url="",
    )

    # Act
    result = await run_graph_runner(
        graph,
        input={
            "mode": "ma",
            "subject_name": "HashiCorp",
            "packet_path": "HASHICORP_FOLDER",
        },
        provider=scripted_llm_ma_happy_path,
        persist=False,
    )

    # Assert — Coordinator created a doc
    assert result.state["verdict_doc_id"], (
        "Coordinator must populate `verdict_doc_id` after create_doc()."
    )

    # Assert — the FakeDocsAdapter has at least one doc registered, with
    # body content that contains M&A section headers (deal memo shape).
    # FakeDocsAdapter exposes `_docs: dict[doc_id, list[str]]`; we read that
    # via the public surface available in the current implementation.
    assert docs._docs, "FakeDocsAdapter received no create_doc / append_text call."
    body_blocks = next(iter(docs._docs.values()))
    full_body = "\n".join(body_blocks)
    expected_section_markers = [
        "Executive Summary",
        "Strategic Fit",
        "Financial Analysis",
        "Risks",
    ]
    missing = [s for s in expected_section_markers if s not in full_body]
    assert not missing, (
        f"Deal memo body missing required sections {missing!r}. "
        f"Body was:\n{full_body[:500]}"
    )


# ---------------------------------------------------------------------------
# Model-routing — M&A specialists use Pro for long-context, vendor uses Flash
# ---------------------------------------------------------------------------

async def test_ma_mode_uses_pro_model_for_long_context(
    seeded_drive_ma,
    seeded_drive_vendor,
    ma_mode_config: Any,
    vendor_mode_config: Any,
    run_graph_runner,
):
    """M&A specialists must be invoked with `model="gemini-2.5-pro"` (or
    whatever the mode_config declares as the long-context model);
    vendor specialists must be invoked with `model="gemini-2.5-flash"`.

    We assert by inspecting the ScriptedLLM `call_log[*]["model"]` field.
    """
    # Arrange — M&A run
    ma_llm = ScriptedLLM([
        LLMResponse(content=json.dumps([
            {"doc": "10-k.pdf", "specialists": ["LegalAgent", "FinancialAgent"]},
        ])),
        LLMResponse(content=json.dumps([])),  # Legal
        LLMResponse(content=json.dumps([])),  # Security
        LLMResponse(content=json.dumps([])),  # External
        LLMResponse(content=json.dumps({"summary": "", "tech_debt": "low"})),  # Code
        LLMResponse(content=json.dumps([])),  # Financial
        LLMResponse(content=json.dumps({
            "Executive Summary": "stub",
            "Strategic Fit": "stub",
            "Financial Analysis": "stub",
            "Technical Diligence": "stub",
            "Risks": "stub",
            "Open Questions": "stub",
        })),  # Coordinator
    ])
    build_graph = graph_module.build_graph
    Adapters = graph_module.Adapters
    ma_adapters = Adapters(
        drive=seeded_drive_ma, files=GeminiFilesAdapter(), sheets=None,
        docs=FakeDocsAdapter(), bq=FakeBigQueryAdapter(), github=None,
    )
    ma_graph = build_graph(
        ma_mode_config, adapters=ma_adapters,
        drive_folder_id="HASHICORP_FOLDER", sheet_id="", doc_id="",
        bq_dataset="ds", bq_table="tbl", github_url="",
    )

    # Arrange — vendor run (control)
    vendor_llm = ScriptedLLM([
        LLMResponse(content=json.dumps([
            {"doc": "msa.pdf", "specialists": ["LegalAgent"]},
            {"doc": "soc2.pdf", "specialists": ["SecurityAgent"]},
        ])),
        LLMResponse(content=json.dumps([])),  # Legal
        LLMResponse(content=json.dumps([])),  # Security
        LLMResponse(content=json.dumps([])),  # External
        LLMResponse(content=json.dumps({"summary": "", "tech_debt": "low"})),  # Code
        LLMResponse(content="OK"),  # Coordinator
    ])
    vendor_adapters = Adapters(
        drive=seeded_drive_vendor, files=GeminiFilesAdapter(),
        sheets=FakeSheetsAdapter(), docs=None,
        bq=FakeBigQueryAdapter(), github=None,
    )
    vendor_graph = build_graph(
        vendor_mode_config, adapters=vendor_adapters,
        drive_folder_id="ACME_FOLDER", sheet_id="SHEET-ACME", doc_id="",
        bq_dataset="ds", bq_table="tbl", github_url="",
    )

    # Act
    await run_graph_runner(
        ma_graph,
        input={"mode": "ma", "subject_name": "HashiCorp", "packet_path": "HASHICORP_FOLDER"},
        provider=ma_llm, persist=False,
    )
    await run_graph_runner(
        vendor_graph,
        input={"mode": "vendor", "subject_name": "Acme", "packet_path": "ACME_FOLDER"},
        provider=vendor_llm, persist=False,
    )

    # Assert — at least one M&A specialist call used a Pro model
    ma_models = {call["model"] for call in ma_llm.call_log if call.get("model")}
    assert any("pro" in (m or "").lower() for m in ma_models), (
        f"Expected at least one M&A specialist to use a Pro model; "
        f"call_log models were {ma_models!r}"
    )

    # Assert — vendor calls used Flash (no Pro)
    vendor_models = {call["model"] for call in vendor_llm.call_log if call.get("model")}
    assert all("pro" not in (m or "").lower() for m in vendor_models), (
        f"Vendor flow must use Flash models only; saw {vendor_models!r}"
    )
    assert any("flash" in (m or "").lower() for m in vendor_models), (
        f"Vendor flow must use Flash models; saw {vendor_models!r}"
    )
