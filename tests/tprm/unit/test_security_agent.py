"""Unit tests for SecurityAgent — SOC2 control coverage specialist.
LLM is mocked via ScriptedLLM; no live Gemini calls."""
from __future__ import annotations

import pytest

from orchestra.core.context import ExecutionContext
from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM
from orchestra_tprm.agents.specialists.security import SecurityAgent
from orchestra_tprm.modes.config import load_mode


@pytest.mark.asyncio
async def test_security_emits_control_gaps():
    cfg = load_mode("vendor")
    agent = SecurityAgent(model=cfg.specialists.security)
    llm = ScriptedLLM(
        [
            LLMResponse(
                content='[{"control_id":"CC6.1","status":"gap","severity":"high","summary":"MFA not enforced for admin","citation_page":4},'
                        '{"control_id":"CC7.2","status":"covered","severity":"low","summary":"Logging in place","citation_page":7}]'
            ),
        ]
    )
    ctx = ExecutionContext(provider=llm)
    ctx.state = {
        "subject_name": "Acme",
        "file_uris": {"soc2.pdf": "local:///tmp/soc2.pdf"},
        "routing": {"SecurityAgent": ["soc2.pdf"]},
    }
    findings = await agent.run(ctx)
    # Both gap and covered findings emit; severity remains as scored by LLM.
    assert len(findings) == 2
    sevs = sorted(f.severity for f in findings)
    assert sevs == ["high", "low"]
    cats = sorted(f.category for f in findings)
    assert cats == ["soc2-cc6.1", "soc2-cc7.2"]


@pytest.mark.asyncio
async def test_security_no_docs_returns_empty():
    """When routing has no docs for SecurityAgent, return empty list."""
    agent = SecurityAgent()
    llm = ScriptedLLM([])
    ctx = ExecutionContext(provider=llm)
    ctx.state = {
        "subject_name": "Acme",
        "file_uris": {},
        "routing": {},
    }
    findings = await agent.run(ctx)
    assert findings == []
    assert llm.call_count == 0


@pytest.mark.asyncio
async def test_security_skips_missing_uri():
    """Docs listed in routing but absent from file_uris are silently skipped."""
    agent = SecurityAgent()
    llm = ScriptedLLM([])
    ctx = ExecutionContext(provider=llm)
    ctx.state = {
        "subject_name": "Acme",
        "file_uris": {},
        "routing": {"SecurityAgent": ["soc2.pdf"]},
    }
    findings = await agent.run(ctx)
    assert findings == []
    assert llm.call_count == 0


@pytest.mark.asyncio
async def test_security_malformed_json_skipped():
    """If LLM returns non-JSON, the doc is skipped without raising."""
    agent = SecurityAgent()
    llm = ScriptedLLM([LLMResponse(content="Sorry, I can't help with that.")])
    ctx = ExecutionContext(provider=llm)
    ctx.state = {
        "subject_name": "Acme",
        "file_uris": {"soc2.pdf": "local:///tmp/soc2.pdf"},
        "routing": {"SecurityAgent": ["soc2.pdf"]},
    }
    findings = await agent.run(ctx)
    assert findings == []


@pytest.mark.asyncio
async def test_security_finding_has_citation():
    """Each finding carries a Citation with the correct file_id and page."""
    agent = SecurityAgent()
    llm = ScriptedLLM(
        [
            LLMResponse(
                content='[{"control_id":"A.9.4","status":"gap","severity":"medium",'
                        '"summary":"Privilege access review missing","citation_page":12}]'
            )
        ]
    )
    ctx = ExecutionContext(provider=llm)
    ctx.state = {
        "subject_name": "Acme",
        "file_uris": {"iso27001.pdf": "local:///tmp/iso27001.pdf"},
        "routing": {"SecurityAgent": ["iso27001.pdf"]},
    }
    findings = await agent.run(ctx)
    assert len(findings) == 1
    f = findings[0]
    assert f.agent == "SecurityAgent"
    assert f.category == "soc2-a.9.4"
    assert f.severity == "medium"
    assert len(f.evidence) == 1
    assert f.evidence[0].file_id == "iso27001.pdf"
    assert f.evidence[0].page == 12


@pytest.mark.asyncio
async def test_security_safety_filter_returns_suppressed_finding():
    """When Gemini safety filter suppresses both attempts, emit filter-suppressed Finding."""
    agent = SecurityAgent()
    llm = ScriptedLLM(
        [
            LLMResponse(content="", finish_reason="safety"),
            LLMResponse(content="", finish_reason="safety"),
        ]
    )
    ctx = ExecutionContext(provider=llm)
    ctx.state = {
        "subject_name": "Acme",
        "file_uris": {"soc2.pdf": "local:///tmp/soc2.pdf"},
        "routing": {"SecurityAgent": ["soc2.pdf"]},
    }
    findings = await agent.run(ctx)
    assert len(findings) == 1
    assert findings[0].category == "filter-suppressed"
    assert findings[0].severity == "medium"
