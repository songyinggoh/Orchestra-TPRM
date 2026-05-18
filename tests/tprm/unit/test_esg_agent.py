# tests/tprm/unit/test_esg_agent.py
"""Unit tests for ESGAgent — 7th specialist for both vendor and M&A modes."""
from __future__ import annotations

import json
from pathlib import Path

from orchestra.core.context import ExecutionContext
from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM

from orchestra_tprm.agents.specialists.esg import ESGAgent


def _make_ctx(provider, *, file_uris=None, routing=None) -> ExecutionContext:
    ctx = ExecutionContext(provider=provider)
    ctx.state = {
        "subject_name": "HashiCorp",
        "file_uris": file_uris or {},
        "routing": routing or {},
    }
    return ctx


async def test_no_routed_docs_emits_informational_finding() -> None:
    agent = ESGAgent(model="gemini-2.5-flash")
    ctx = _make_ctx(ScriptedLLM([]), routing={"ESGAgent": []})
    findings = await agent.run(ctx)
    assert len(findings) == 1
    assert findings[0].category == "esg-no-docs"
    assert findings[0].severity == "low"


async def test_net_zero_gap_emits_critical_finding(tmp_path: Path) -> None:
    doc = tmp_path / "sustainability.txt"
    doc.write_text("We aim to reduce our environmental impact.")
    agent = ESGAgent(model="gemini-2.5-flash")
    llm = ScriptedLLM([LLMResponse(content=json.dumps([
        {
            "category": "net-zero-commitment",
            "severity": "critical",
            "summary": "No net-zero target year disclosed in sustainability report.",
            "citation_page": 1,
        }
    ]))])
    ctx = _make_ctx(
        llm,
        file_uris={"sustainability.txt": f"local://{doc.as_posix()}"},
        routing={"ESGAgent": ["sustainability.txt"]},
    )
    findings = await agent.run(ctx)
    assert len(findings) == 1
    f = findings[0]
    assert f.category == "net-zero-commitment"
    assert f.severity == "critical"
    assert f.agent == "ESGAgent"


async def test_modern_slavery_high_severity(tmp_path: Path) -> None:
    doc = tmp_path / "governance.txt"
    doc.write_text("Standard governance disclosures...")
    agent = ESGAgent(model="gemini-2.5-flash")
    llm = ScriptedLLM([LLMResponse(content=json.dumps([
        {
            "category": "modern-slavery-statement",
            "severity": "high",
            "summary": "No modern slavery statement found in governance disclosures.",
            "citation_page": 3,
        }
    ]))])
    ctx = _make_ctx(
        llm,
        file_uris={"governance.txt": f"local://{doc.as_posix()}"},
        routing={"ESGAgent": ["governance.txt"]},
    )
    findings = await agent.run(ctx)
    assert findings[0].severity == "high"


async def test_clean_disclosure_returns_empty(tmp_path: Path) -> None:
    doc = tmp_path / "esg.txt"
    doc.write_text("Net-zero by 2040, full MSA disclosure, board 50% independent.")
    agent = ESGAgent(model="gemini-2.5-flash")
    llm = ScriptedLLM([LLMResponse(content="[]")])
    ctx = _make_ctx(
        llm,
        file_uris={"esg.txt": f"local://{doc.as_posix()}"},
        routing={"ESGAgent": ["esg.txt"]},
    )
    findings = await agent.run(ctx)
    assert findings == []
