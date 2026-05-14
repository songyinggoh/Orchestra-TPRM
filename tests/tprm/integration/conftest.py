"""Integration-test fixtures for Orchestra-TPRM end-to-end flows.

These fixtures define the CONTRACT that Tasks 14-28 must satisfy:

  - `seeded_drive_vendor` / `seeded_drive_ma`  → FakeDriveAdapter pre-populated
    with synthetic packet content (just enough text to be recognisable).
  - `scripted_llm_vendor_happy_path` / `scripted_llm_ma_happy_path`  → ScriptedLLM
    with one canned JSON response per specialist call.
  - `adapters_bundle` → namespace of Fake* adapters wired together.
  - `vendor_mode_config` / `ma_mode_config` → ModeConfig instances loaded
    (lazily, via importorskip) from `orchestra_tprm.modes.config`.

INVARIANT — until `orchestra_tprm.graph` lands, every test module using these
fixtures must call `pytest.importorskip("orchestra_tprm.graph")` at module
top. Missing dependencies = SKIP. Broken contract = FAIL.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM
from orchestra_tprm.adapters import (
    FakeBigQueryAdapter,
    FakeDocsAdapter,
    FakeDriveAdapter,
    FakeSheetsAdapter,
    GeminiFilesAdapter,
)


# ---------------------------------------------------------------------------
# Synthetic packet content — 5–10 lines per doc, not full documents
# ---------------------------------------------------------------------------

ACME_MSA_SNIPPET = b"""MASTER SERVICES AGREEMENT
Acme Cloud Analytics, Inc. ("Provider") and Customer hereby agree:
8.2 LIABILITY CAP. Provider's aggregate liability under this Agreement
shall not exceed one (1) times the fees paid by Customer in the
twelve (12) months preceding the claim.
12.1 TERMINATION. Either party may terminate for material breach with
thirty (30) days' written notice and a cure period.
"""

ACME_SOC2_SNIPPET = b"""SOC 2 TYPE II REPORT -- ACME CLOUD ANALYTICS
Trust Services Criteria assessed: Security, Availability, Confidentiality.
CC6.1 Logical Access Controls: GAP IDENTIFIED -- multi-factor authentication
is not enforced for administrative console access.
CC7.2 System Monitoring: Effective.
Auditor: Coalfire LLP. Period: 2025-01-01 through 2025-12-31.
"""

HASHICORP_10K_SNIPPET = b"""HASHICORP, INC. -- FORM 10-K (Excerpt)
Item 7. Management's Discussion and Analysis
Revenue grew 15% year-over-year to $583M; operating margin remained
negative at (12%) reflecting continued go-to-market investment.
Item 1A. Risk Factors
In August 2023 we transitioned core products to the Business Source
License (BSL); the OpenTofu fork has fragmented portions of the
Terraform community.
Section 15.2 (Change of Control): A change of control triggers
acceleration of unvested equity for executive officers.
"""


# ---------------------------------------------------------------------------
# Drive fixtures — seeded with synthetic packet content
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded_drive_vendor() -> FakeDriveAdapter:
    """FakeDriveAdapter pre-populated with a synthetic Acme MSA + SOC 2 packet.

    Folder layout (id="ACME_FOLDER"):
        msa.pdf            → ACME_MSA_SNIPPET
        soc2.pdf           → ACME_SOC2_SNIPPET
    """
    adapter = FakeDriveAdapter()
    adapter.seed_folder(
        folder_id="ACME_FOLDER",
        files=[
            {"id": "msa.pdf", "name": "msa.pdf", "kind": "contract"},
            {"id": "soc2.pdf", "name": "soc2.pdf", "kind": "security_attestation"},
        ],
        contents={
            "msa.pdf": ACME_MSA_SNIPPET,
            "soc2.pdf": ACME_SOC2_SNIPPET,
        },
    )
    return adapter


@pytest.fixture
def seeded_drive_ma() -> FakeDriveAdapter:
    """FakeDriveAdapter pre-populated with a synthetic HashiCorp 10-K excerpt.

    Folder layout (id="HASHICORP_FOLDER"):
        10-k.pdf           → HASHICORP_10K_SNIPPET
    """
    adapter = FakeDriveAdapter()
    adapter.seed_folder(
        folder_id="HASHICORP_FOLDER",
        files=[
            {"id": "10-k.pdf", "name": "10-k.pdf", "kind": "financial_filing"},
        ],
        contents={
            "10-k.pdf": HASHICORP_10K_SNIPPET,
        },
    )
    return adapter


# ---------------------------------------------------------------------------
# ScriptedLLM fixtures — one response per expected specialist call
# ---------------------------------------------------------------------------
#
# The order MUST match the deterministic asyncio.gather() ordering inside
# build_graph()'s parallel fan-out (router emits decisions first, then each
# specialist is awaited in the order they were registered: legal, security,
# external, code, financial). Coordinator runs last.

def _vendor_responses() -> list[LLMResponse]:
    return [
        # Router — assigns each doc to specialists
        LLMResponse(
            content=json.dumps([
                {"doc": "msa.pdf", "specialists": ["LegalAgent"]},
                {"doc": "soc2.pdf", "specialists": ["SecurityAgent"]},
            ])
        ),
        # LegalAgent
        LLMResponse(
            content=json.dumps([{
                "category": "liability",
                "severity": "high",
                "summary": "Liability cap is 1x annual fees — below 12-month industry norm.",
                "citation_page": 12,
                "clause_id": "8.2",
            }])
        ),
        # SecurityAgent
        LLMResponse(
            content=json.dumps([{
                "control_id": "CC6.1",
                "category": "soc2-cc6.1",
                "status": "gap",
                "severity": "medium",
                "summary": "MFA is not enforced for administrative console access.",
                "citation_page": 4,
            }])
        ),
        # ExternalAgent
        LLMResponse(
            content=json.dumps([{
                "category": "sanctions",
                "severity": "low",
                "summary": "No sanctions or adverse media hits found.",
                "source_url": "https://example.com/sanctions-clear",
            }])
        ),
        # CodeAgent (vendor mode = license audit only — single short summary)
        LLMResponse(
            content=json.dumps({
                "summary": "Repository license is MIT, no obvious tech-debt signals.",
                "tech_debt": "low",
            })
        ),
        # Coordinator (writes deal-memo / approval-form body)
        LLMResponse(
            content="Recommendation: CONDITIONAL APPROVE. Renegotiate liability cap to 12x annual fees."
        ),
    ]


def _ma_responses() -> list[LLMResponse]:
    return [
        # Router
        LLMResponse(
            content=json.dumps([
                {"doc": "10-k.pdf", "specialists": ["LegalAgent", "FinancialAgent"]},
            ])
        ),
        # LegalAgent — change-of-control clause
        LLMResponse(
            content=json.dumps([{
                "category": "change-of-control",
                "severity": "medium",
                "summary": "Change-of-control triggers acceleration of executive equity.",
                "citation_page": 143,
                "clause_id": "15.2",
            }])
        ),
        # SecurityAgent — no routed docs, but the parallel branch still
        # executes; the LLM call returns an empty list. If the spec opts
        # to SKIP the call entirely we provide enough script and rely on
        # the test's `assert_all_consumed=False` semantics.
        LLMResponse(content=json.dumps([])),
        # ExternalAgent
        LLMResponse(
            content=json.dumps([{
                "category": "ma-history",
                "severity": "low",
                "summary": "IBM acquisition rumours circulating; no confirmed deal.",
                "source_url": "https://example.com/news",
            }])
        ),
        # CodeAgent (M&A mode = full repo audit)
        LLMResponse(
            content=json.dumps({
                "summary": "BSL license transition in 2023 fragmented community; OpenTofu fork emerged.",
                "tech_debt": "medium",
            })
        ),
        # FinancialAgent
        LLMResponse(
            content=json.dumps([
                {
                    "metric": "revenue_growth_yoy",
                    "value": "+15%",
                    "severity": "low",
                    "summary": "Revenue grew 15% YoY to $583M.",
                    "citation_page": 42,
                },
                {
                    "metric": "operating_margin",
                    "value": "-12%",
                    "severity": "high",
                    "summary": "Operating margin remains negative at (12%).",
                    "citation_page": 42,
                },
            ])
        ),
        # Coordinator — deal-memo sections
        LLMResponse(
            content=json.dumps({
                "Executive Summary": "HashiCorp acquisition: conditional approve.",
                "Strategic Fit": "Strong cloud-native infrastructure fit.",
                "Financial Analysis": "Revenue growth solid; margins negative.",
                "Technical Diligence": "BSL license is the headline risk.",
                "Risks": "License fragmentation, OpenTofu fork, customer churn risk.",
                "Open Questions": "Customer retention since BSL transition?",
            })
        ),
    ]


@pytest.fixture
def scripted_llm_vendor_happy_path() -> ScriptedLLM:
    """ScriptedLLM with realistic JSON responses for the vendor flow.

    Order matches build_graph()'s deterministic fan-out:
        Router → Legal → Security → External → Code → Coordinator
    """
    return ScriptedLLM(_vendor_responses())


@pytest.fixture
def scripted_llm_ma_happy_path() -> ScriptedLLM:
    """ScriptedLLM with realistic JSON responses for the M&A flow.

    Order matches build_graph()'s deterministic fan-out:
        Router → Legal → Security → External → Code → Financial → Coordinator
    """
    return ScriptedLLM(_ma_responses())


# ---------------------------------------------------------------------------
# Adapters bundle — a tiny namespace of Fake* adapters
# ---------------------------------------------------------------------------
#
# Mirrors the planned `orchestra_tprm.graph.Adapters` dataclass but uses only
# the currently-existing Fake adapter APIs. Once `graph.Adapters` lands,
# tests can switch to constructing it directly from this bundle.

@dataclass
class AdaptersBundle:
    """Container for all Fake adapters used by an integration test."""
    drive: FakeDriveAdapter
    files: GeminiFilesAdapter
    sheets: FakeSheetsAdapter
    docs: FakeDocsAdapter
    bq: FakeBigQueryAdapter


@pytest.fixture
def adapters_bundle(seeded_drive_vendor: FakeDriveAdapter) -> AdaptersBundle:
    """Default adapters_bundle uses the vendor drive seed.

    Tests that need the M&A drive should construct their own bundle by
    swapping in the `seeded_drive_ma` fixture (see test_ma_mode.py).
    """
    return AdaptersBundle(
        drive=seeded_drive_vendor,
        files=GeminiFilesAdapter(),
        sheets=FakeSheetsAdapter(),
        docs=FakeDocsAdapter(),
        bq=FakeBigQueryAdapter(),
    )


# ---------------------------------------------------------------------------
# Mode-config fixtures — loaded lazily to keep collection clean
# ---------------------------------------------------------------------------

@pytest.fixture
def vendor_mode_config() -> Any:
    """Returns the parsed vendor ModeConfig.

    SKIPS the test if `orchestra_tprm.modes.config` does not exist yet —
    that module lands in Task ~14 alongside the mode YAML loader.
    """
    config_mod = pytest.importorskip("orchestra_tprm.modes.config")
    load_mode = getattr(config_mod, "load_mode", None)
    if load_mode is None:
        pytest.skip("orchestra_tprm.modes.config.load_mode not yet implemented")
    return load_mode("vendor")


@pytest.fixture
def ma_mode_config() -> Any:
    """Returns the parsed M&A ModeConfig.

    SKIPS the test if `orchestra_tprm.modes.config` does not exist yet.
    """
    config_mod = pytest.importorskip("orchestra_tprm.modes.config")
    load_mode = getattr(config_mod, "load_mode", None)
    if load_mode is None:
        pytest.skip("orchestra_tprm.modes.config.load_mode not yet implemented")
    return load_mode("ma")


# ---------------------------------------------------------------------------
# Graph runner — thin wrapper that documents the expected call shape
# ---------------------------------------------------------------------------

@pytest.fixture
def run_graph_runner():
    """Returns the orchestra.core.runner.run callable, asserting it exists.

    Centralised so tests don't all do `from orchestra.core.runner import run`.
    """
    from orchestra.core.runner import run as _run
    return _run
