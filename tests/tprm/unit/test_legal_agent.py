"""Unit tests for LegalAgent — all LLM calls mocked via ScriptedLLM.

TDD: these tests were written before legal.py existed.
"""
from __future__ import annotations

import pytest

from orchestra.core.context import ExecutionContext
from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM
from orchestra_tprm.agents.specialists.legal import LegalAgent
from orchestra_tprm.modes.config import load_mode


@pytest.mark.asyncio
async def test_legal_emits_findings_for_each_clause_returned():
    cfg = load_mode("vendor")
    agent = LegalAgent(model=cfg.specialists.legal)
    llm = ScriptedLLM(
        [
            LLMResponse(
                content=(
                    '[{"category":"liability","severity":"high",'
                    '"summary":"Cap is 1x annual fees","citation_page":12,"clause_id":"8.2"},'
                    '{"category":"ip-assignment","severity":"medium",'
                    '"summary":"All IP assigned to vendor","citation_page":15,"clause_id":"11.1"}]'
                )
            ),
        ]
    )
    ctx = ExecutionContext(provider=llm)
    ctx.state = {
        "subject_name": "Acme",
        "file_uris": {"msa.pdf": "local:///tmp/msa.pdf"},
        "routing": {"LegalAgent": ["msa.pdf"]},
    }
    findings = await agent.run(ctx)
    assert len(findings) == 2
    cats = sorted(f.category for f in findings)
    assert cats == ["ip-assignment", "liability"]
    assert all(f.agent == "LegalAgent" for f in findings)
    # Citations carry through
    assert findings[0].evidence[0].file_id == "msa.pdf"


@pytest.mark.asyncio
async def test_legal_handles_empty_routing_gracefully():
    cfg = load_mode("vendor")
    agent = LegalAgent(model=cfg.specialists.legal)
    ctx = ExecutionContext(provider=ScriptedLLM([]))
    ctx.state = {"subject_name": "Acme", "file_uris": {}, "routing": {}}
    findings = await agent.run(ctx)
    assert findings == []


@pytest.mark.asyncio
async def test_legal_skips_missing_uri():
    """Document listed in routing but absent from file_uris is silently skipped."""
    agent = LegalAgent()
    ctx = ExecutionContext(provider=ScriptedLLM([]))
    ctx.state = {
        "subject_name": "Beta",
        "file_uris": {},
        "routing": {"LegalAgent": ["missing.pdf"]},
    }
    findings = await agent.run(ctx)
    assert findings == []


@pytest.mark.asyncio
async def test_legal_emits_parse_error_on_malformed_json():
    """If the LLM returns non-JSON text, LegalAgent emits a parse-error
    Finding (was silent-skip pre-S4; aligned with Code+External pattern)."""
    agent = LegalAgent()
    llm = ScriptedLLM([LLMResponse(content="not json at all")])
    ctx = ExecutionContext(provider=llm)
    ctx.state = {
        "subject_name": "Gamma",
        "file_uris": {"contract.pdf": "local:///tmp/contract.pdf"},
        "routing": {"LegalAgent": ["contract.pdf"]},
    }
    findings = await agent.run(ctx)
    assert len(findings) == 1
    assert findings[0].category == "parse-error"
    assert findings[0].severity == "high"
    assert findings[0].agent == "LegalAgent"
    assert findings[0].evidence[0].file_id == "contract.pdf"


@pytest.mark.asyncio
async def test_legal_default_model_is_flash():
    agent = LegalAgent()
    assert agent.model == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_legal_citation_page_and_clause_id_carried():
    """Citation page and clause_id (as snippet) are preserved on each Finding."""
    agent = LegalAgent()
    llm = ScriptedLLM(
        [
            LLMResponse(
                content=(
                    '[{"category":"indemnity","severity":"critical",'
                    '"summary":"Uncapped indemnification","citation_page":8,"clause_id":"12.3"}]'
                )
            )
        ]
    )
    ctx = ExecutionContext(provider=llm)
    ctx.state = {
        "subject_name": "Delta",
        "file_uris": {"nda.pdf": "local:///tmp/nda.pdf"},
        "routing": {"LegalAgent": ["nda.pdf"]},
    }
    findings = await agent.run(ctx)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == "critical"
    assert finding.category == "indemnity"
    citation = finding.evidence[0]
    assert citation.page == 8
    assert citation.snippet == "12.3"
    assert citation.file_id == "nda.pdf"


@pytest.mark.asyncio
async def test_legal_safety_retry_yields_filter_suppressed():
    """W-3: two consecutive safety-filtered responses produce a filter-suppressed Finding."""
    agent = LegalAgent()
    llm = ScriptedLLM(
        [
            LLMResponse(content="", finish_reason="safety"),
            LLMResponse(content="", finish_reason="safety"),
        ]
    )
    ctx = ExecutionContext(provider=llm)
    ctx.state = {
        "subject_name": "Echo",
        "file_uris": {"risky.pdf": "local:///tmp/risky.pdf"},
        "routing": {"LegalAgent": ["risky.pdf"]},
    }
    findings = await agent.run(ctx)
    assert len(findings) == 1
    assert findings[0].category == "filter-suppressed"
    assert findings[0].severity == "medium"
    assert findings[0].agent == "LegalAgent"
