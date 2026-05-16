"""Unit tests for all 5 TPRM specialist agents.

All LLM calls are mocked via ScriptedLLM — no live Gemini calls.
asyncio_mode = "auto" is set in pyproject.toml so no @pytest.mark.asyncio needed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestra.core.context import ExecutionContext
from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM
from orchestra_tprm.agents.specialists import (
    CodeAgent,
    ExternalAgent,
    FinancialAgent,
    LegalAgent,
    SecurityAgent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(
    provider,
    *,
    subject_name: str = "TestCo",
    file_uris: dict | None = None,
    routing: dict | None = None,
) -> ExecutionContext:
    ctx = ExecutionContext(provider=provider)
    ctx.state = {
        "subject_name": subject_name,
        "file_uris": file_uris or {},
        "routing": routing or {},
    }
    return ctx


# ---------------------------------------------------------------------------
# LegalAgent
# ---------------------------------------------------------------------------

async def test_legal_agent_parses_llm_response(tmp_path: Path) -> None:
    contract = tmp_path / "msa.txt"
    contract.write_text("This agreement limits liability to 1x annual fees.")

    llm = ScriptedLLM([
        LLMResponse(content=json.dumps([
            {
                "category": "liability",
                "severity": "high",
                "summary": "Cap is 1x annual fees",
                "citation_page": 3,
                "clause_id": "8.2",
            }
        ]))
    ])
    agent = LegalAgent(model="gemini-2.5-flash")
    ctx = _make_ctx(
        llm,
        file_uris={"msa.txt": f"local://{contract}"},
        routing={"LegalAgent": ["msa.txt"]},
    )
    findings = await agent.run(ctx)

    assert len(findings) == 1
    f = findings[0]
    assert f.agent == "LegalAgent"
    assert f.category == "liability"
    assert f.severity == "high"
    assert f.evidence[0].file_id == "msa.txt"


async def test_legal_agent_empty_uris_returns_no_findings() -> None:
    agent = LegalAgent(model="gemini-2.5-flash")
    ctx = _make_ctx(ScriptedLLM([]), routing={}, file_uris={})
    findings = await agent.run(ctx)
    assert findings == []


async def test_legal_agent_skips_missing_uri() -> None:
    agent = LegalAgent()
    ctx = _make_ctx(
        ScriptedLLM([]),
        file_uris={},
        routing={"LegalAgent": ["missing.pdf"]},
    )
    findings = await agent.run(ctx)
    assert findings == []


async def test_legal_agent_citation_page_and_clause_id(tmp_path: Path) -> None:
    doc = tmp_path / "nda.txt"
    doc.write_text("Non-disclosure agreement content.")

    llm = ScriptedLLM([
        LLMResponse(content=json.dumps([
            {
                "category": "indemnity",
                "severity": "critical",
                "summary": "Uncapped indemnification",
                "citation_page": 8,
                "clause_id": "12.3",
            }
        ]))
    ])
    agent = LegalAgent()
    ctx = _make_ctx(
        llm,
        file_uris={"nda.txt": f"local://{doc}"},
        routing={"LegalAgent": ["nda.txt"]},
    )
    findings = await agent.run(ctx)
    assert len(findings) == 1
    citation = findings[0].evidence[0]
    assert citation.page == 8
    assert citation.snippet == "12.3"
    assert citation.file_id == "nda.txt"


# ---------------------------------------------------------------------------
# SecurityAgent
# ---------------------------------------------------------------------------

async def test_security_agent_parses_llm_response(tmp_path: Path) -> None:
    soc2 = tmp_path / "soc2.txt"
    soc2.write_text("SOC 2 Type II report content.")

    llm = ScriptedLLM([
        LLMResponse(content=json.dumps([
            {
                "control_id": "CC6.1",
                "status": "gap",
                "severity": "high",
                "summary": "MFA not enforced for admin accounts",
                "citation_page": 4,
            }
        ]))
    ])
    agent = SecurityAgent(model="gemini-2.5-flash")
    ctx = _make_ctx(
        llm,
        file_uris={"soc2.txt": f"local://{soc2}"},
        routing={"SecurityAgent": ["soc2.txt"]},
    )
    findings = await agent.run(ctx)

    assert len(findings) == 1
    f = findings[0]
    assert f.agent == "SecurityAgent"
    assert f.category == "soc2-cc6.1"
    assert f.severity == "high"
    assert f.evidence[0].file_id == "soc2.txt"
    assert f.evidence[0].page == 4


async def test_security_agent_empty_routing_returns_no_findings() -> None:
    agent = SecurityAgent()
    ctx = _make_ctx(ScriptedLLM([]), routing={}, file_uris={})
    findings = await agent.run(ctx)
    assert findings == []


async def test_security_agent_no_llm_call_when_no_docs() -> None:
    llm = ScriptedLLM([])
    agent = SecurityAgent()
    ctx = _make_ctx(llm, routing={}, file_uris={})
    await agent.run(ctx)
    assert llm.call_count == 0


# ---------------------------------------------------------------------------
# CodeAgent
# ---------------------------------------------------------------------------

async def test_code_agent_single_dict_response(tmp_path: Path) -> None:
    repo_meta = tmp_path / "repo.txt"
    repo_meta.write_text("Python 3.8, 45% test coverage, MIT license.")

    llm = ScriptedLLM([
        LLMResponse(content=json.dumps({
            "summary": "Moderate tech debt with low test coverage",
            "tech_debt": "medium",
            "license": "MIT",
            "patch_needed": False,
        }))
    ])
    agent = CodeAgent(model="gemini-2.5-flash")
    ctx = _make_ctx(
        llm,
        file_uris={"repo.txt": f"local://{repo_meta}"},
        routing={"CodeAgent": ["repo.txt"]},
    )
    findings = await agent.run(ctx)

    assert len(findings) == 1
    f = findings[0]
    assert f.agent == "CodeAgent"
    assert f.category == "code-risk"
    assert f.severity == "medium"
    assert "tech debt" in f.summary.lower()


async def test_code_agent_tech_debt_severity_mapping(tmp_path: Path) -> None:
    repo = tmp_path / "repo.txt"
    repo.write_text("Repo metadata.")

    for tech_debt, expected_severity in [("low", "low"), ("medium", "medium"), ("high", "high")]:
        llm = ScriptedLLM([
            LLMResponse(content=json.dumps({
                "summary": f"Tech debt: {tech_debt}",
                "tech_debt": tech_debt,
                "license": "Apache-2.0",
                "patch_needed": False,
            }))
        ])
        agent = CodeAgent()
        ctx = _make_ctx(
            llm,
            file_uris={"repo.txt": f"local://{repo}"},
            routing={"CodeAgent": ["repo.txt"]},
        )
        findings = await agent.run(ctx)
        assert len(findings) == 1
        assert findings[0].severity == expected_severity, (
            f"tech_debt={tech_debt!r} → expected severity={expected_severity!r}, "
            f"got {findings[0].severity!r}"
        )


async def test_code_agent_unknown_tech_debt_with_patch_needed_is_critical(tmp_path: Path) -> None:
    """patch_needed=True overrides tech_debt mapping — even an unknown tech_debt level becomes critical."""
    repo = tmp_path / "repo.txt"
    repo.write_text("Repo.")

    llm = ScriptedLLM([
        LLMResponse(content=json.dumps({
            "summary": "Unclear tech debt level",
            "tech_debt": "very-high",
            "license": None,
            "patch_needed": True,
        }))
    ])
    agent = CodeAgent()
    ctx = _make_ctx(
        llm,
        file_uris={"repo.txt": f"local://{repo}"},
        routing={"CodeAgent": ["repo.txt"]},
    )
    findings = await agent.run(ctx)
    assert findings[0].severity == "critical"


async def test_code_agent_unknown_tech_debt_no_patch_defaults_to_medium(tmp_path: Path) -> None:
    """Unknown tech_debt without patch_needed falls back to medium."""
    repo = tmp_path / "repo.txt"
    repo.write_text("Repo.")

    llm = ScriptedLLM([
        LLMResponse(content=json.dumps({
            "summary": "Unclear tech debt level",
            "tech_debt": "very-high",
            "license": None,
            "patch_needed": False,
        }))
    ])
    agent = CodeAgent()
    ctx = _make_ctx(
        llm,
        file_uris={"repo.txt": f"local://{repo}"},
        routing={"CodeAgent": ["repo.txt"]},
    )
    findings = await agent.run(ctx)
    assert findings[0].severity == "medium"


async def test_code_agent_empty_routing_returns_no_findings() -> None:
    agent = CodeAgent()
    ctx = _make_ctx(ScriptedLLM([]), routing={}, file_uris={})
    findings = await agent.run(ctx)
    assert findings == []


# ---------------------------------------------------------------------------
# ExternalAgent
# ---------------------------------------------------------------------------

async def test_external_agent_returns_finding(tmp_path: Path) -> None:
    supp = tmp_path / "adverse.txt"
    supp.write_text("Subject appeared in news related to bribery case in 2023.")

    llm = ScriptedLLM([
        LLMResponse(content=json.dumps([
            {
                "category": "adverse-media",
                "severity": "high",
                "summary": "Bribery allegation reported in 2023",
                "source_url": "https://news.example.com/bribery",
            }
        ]))
    ])
    agent = ExternalAgent(model="gemini-2.5-flash")
    ctx = _make_ctx(
        llm,
        subject_name="Acme Corp",
        file_uris={"adverse.txt": f"local://{supp}"},
        routing={"ExternalAgent": ["adverse.txt"]},
    )
    findings = await agent.run(ctx)

    assert len(findings) == 1
    f = findings[0]
    assert f.agent == "ExternalAgent"
    assert f.category == "adverse-media"
    assert f.severity == "high"
    assert f.raw.get("source_url") == "https://news.example.com/bribery"


async def test_external_agent_no_docs_still_runs() -> None:
    """ExternalAgent runs on subject name alone (no supplementary docs)."""
    llm = ScriptedLLM([
        LLMResponse(content=json.dumps([
            {
                "category": "sanctions",
                "severity": "critical",
                "summary": "Entity listed on OFAC SDN list",
                "source_url": None,
            }
        ]))
    ])
    agent = ExternalAgent()
    ctx = _make_ctx(llm, subject_name="BadCo", routing={}, file_uris={})
    findings = await agent.run(ctx)
    assert len(findings) == 1
    assert findings[0].category == "sanctions"


# ---------------------------------------------------------------------------
# FinancialAgent
# ---------------------------------------------------------------------------

async def test_financial_agent_returns_findings(tmp_path: Path) -> None:
    filing = tmp_path / "10k.txt"
    filing.write_text("Revenue declined 20% YoY. Debt-to-equity ratio is 4.2.")

    llm = ScriptedLLM([
        LLMResponse(content=json.dumps([
            {
                "metric": "revenue-growth",
                "value": "-20% YoY",
                "severity": "high",
                "summary": "Revenue declined 20% year-over-year",
                "citation_page": 12,
            },
            {
                "metric": "debt-to-equity",
                "value": "4.2",
                "severity": "medium",
                "summary": "Elevated leverage ratio",
                "citation_page": 18,
            },
        ]))
    ])
    agent = FinancialAgent(model="gemini-2.5-pro")
    ctx = _make_ctx(
        llm,
        file_uris={"10k.txt": f"local://{filing}"},
        routing={"FinancialAgent": ["10k.txt"]},
    )
    findings = await agent.run(ctx)

    assert len(findings) == 2
    cats = sorted(f.category for f in findings)
    assert cats == ["debt-to-equity", "revenue-growth"]
    assert all(f.agent == "FinancialAgent" for f in findings)
    high_f = next(f for f in findings if f.category == "revenue-growth")
    assert high_f.severity == "high"
    assert high_f.evidence[0].page == 12
    assert high_f.raw["metric"] == "revenue-growth"
    assert high_f.raw["value"] == "-20% YoY"


async def test_financial_agent_empty_routing_returns_no_findings() -> None:
    agent = FinancialAgent()
    ctx = _make_ctx(ScriptedLLM([]), routing={}, file_uris={})
    findings = await agent.run(ctx)
    assert findings == []


# ---------------------------------------------------------------------------
# All specialists — empty routing → empty findings (parametrize)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("agent_cls", [
    LegalAgent,
    SecurityAgent,
    CodeAgent,
    FinancialAgent,
])
async def test_all_specialists_return_empty_on_empty_routing(agent_cls) -> None:
    """All specialists return [] when routing has no entries for them."""
    agent = agent_cls()
    ctx = _make_ctx(ScriptedLLM([]), routing={}, file_uris={})
    findings = await agent.run(ctx)
    assert findings == [], f"{agent_cls.__name__} returned non-empty list with empty routing"


# ExternalAgent is separate: it still calls LLM even with no docs.
async def test_external_agent_empty_routing_still_calls_llm() -> None:
    llm = ScriptedLLM([LLMResponse(content="[]")])
    agent = ExternalAgent()
    ctx = _make_ctx(llm, routing={}, file_uris={})
    findings = await agent.run(ctx)
    assert findings == []
    # LLM was still called (subject-name-only screen)
    assert llm.call_count == 1


# ---------------------------------------------------------------------------
# Parse error handling — critical Finding on malformed JSON
# ---------------------------------------------------------------------------

async def test_legal_parse_error_emits_finding(tmp_path: Path) -> None:
    """LegalAgent emits a parse-error Finding on non-JSON (S4: aligned
    with Code+External pattern, was silent-skip pre-S4)."""
    doc = tmp_path / "contract.txt"
    doc.write_text("Contract text.")

    llm = ScriptedLLM([LLMResponse(content="not json at all")])
    agent = LegalAgent()
    ctx = _make_ctx(
        llm,
        file_uris={"contract.txt": f"local://{doc}"},
        routing={"LegalAgent": ["contract.txt"]},
    )
    findings = await agent.run(ctx)
    assert len(findings) == 1
    assert findings[0].category == "parse-error"
    assert findings[0].agent == "LegalAgent"


async def test_security_parse_error_emits_finding(tmp_path: Path) -> None:
    """SecurityAgent emits a parse-error Finding on non-JSON (S4: aligned
    with Code+External pattern, was silent-skip pre-S4)."""
    doc = tmp_path / "soc2.txt"
    doc.write_text("SOC2 text.")

    llm = ScriptedLLM([LLMResponse(content="Sorry, I cannot help.")])
    agent = SecurityAgent()
    ctx = _make_ctx(
        llm,
        file_uris={"soc2.txt": f"local://{doc}"},
        routing={"SecurityAgent": ["soc2.txt"]},
    )
    findings = await agent.run(ctx)
    assert len(findings) == 1
    assert findings[0].category == "parse-error"
    assert findings[0].agent == "SecurityAgent"


async def test_specialist_parse_error_returns_critical_finding(tmp_path: Path) -> None:
    """CodeAgent returns a parse-error Finding (not silent skip) on malformed JSON."""
    repo = tmp_path / "repo.txt"
    repo.write_text("Repo content.")

    llm = ScriptedLLM([LLMResponse(content="not valid json {{{")])
    agent = CodeAgent()
    ctx = _make_ctx(
        llm,
        file_uris={"repo.txt": f"local://{repo}"},
        routing={"CodeAgent": ["repo.txt"]},
    )
    findings = await agent.run(ctx)

    assert len(findings) == 1
    assert findings[0].category == "parse-error"
    assert findings[0].severity == "critical"
    assert findings[0].agent == "CodeAgent"


async def test_external_parse_error_returns_critical_finding(tmp_path: Path) -> None:
    """ExternalAgent returns a parse-error Finding on malformed JSON."""
    llm = ScriptedLLM([LLMResponse(content="{{invalid json}}")])
    agent = ExternalAgent()
    ctx = _make_ctx(llm, routing={}, file_uris={})
    findings = await agent.run(ctx)

    assert len(findings) == 1
    assert findings[0].category == "parse-error"
    assert findings[0].severity == "critical"
    assert findings[0].agent == "ExternalAgent"


async def test_financial_parse_error_returns_critical_finding(tmp_path: Path) -> None:
    """FinancialAgent returns a parse-error Finding on malformed JSON."""
    filing = tmp_path / "10k.txt"
    filing.write_text("Filing content.")

    llm = ScriptedLLM([LLMResponse(content="not-json")])
    agent = FinancialAgent()
    ctx = _make_ctx(
        llm,
        file_uris={"10k.txt": f"local://{filing}"},
        routing={"FinancialAgent": ["10k.txt"]},
    )
    findings = await agent.run(ctx)

    assert len(findings) == 1
    assert findings[0].category == "parse-error"
    assert findings[0].severity == "critical"
    assert findings[0].agent == "FinancialAgent"


# ---------------------------------------------------------------------------
# URI utility
# ---------------------------------------------------------------------------

async def test_read_uri_local(tmp_path: Path) -> None:
    from orchestra_tprm.agents._uri import read_uri

    f = tmp_path / "test.txt"
    f.write_text("hello world")
    result = read_uri(f"local://{f}")
    assert result == "hello world"


async def test_read_uri_non_local_returns_empty() -> None:
    from orchestra_tprm.agents._uri import read_uri

    assert read_uri("https://example.com/file.pdf") == ""
    assert read_uri("gs://bucket/file.pdf") == ""
    assert read_uri("") == ""
