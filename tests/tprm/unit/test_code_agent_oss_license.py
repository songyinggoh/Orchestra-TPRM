"""Unit tests for CodeAgent OSS license contamination pass (Plan 02 / REQ-08)."""
from __future__ import annotations

import json
from pathlib import Path

from orchestra.core.context import ExecutionContext
from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM
from orchestra_tprm.agents.specialists.code import CodeAgent


def _make_ctx_ma(provider, *, file_uris=None, routing=None, ma_scope=None) -> ExecutionContext:
    ctx = ExecutionContext(provider=provider)
    ctx.state = {
        "subject_name": "TargetCorp",
        "file_uris": file_uris or {},
        "routing": routing or {},
        "mode": "ma",
        "ma_scope": ma_scope,
    }
    return ctx


def _make_ctx_vendor(provider, *, file_uris=None, routing=None) -> ExecutionContext:
    ctx = ExecutionContext(provider=provider)
    ctx.state = {
        "subject_name": "TargetCorp",
        "file_uris": file_uris or {},
        "routing": routing or {},
        "mode": "vendor",
    }
    return ctx


async def test_gpl_in_ma_mode_emits_deal_stopper(tmp_path: Path) -> None:
    doc = tmp_path / "code.py"
    doc.write_text("# fake source")
    agent = CodeAgent(model="gemini-2.5-flash")
    llm = ScriptedLLM([LLMResponse(content=json.dumps({
        "summary": "GPL-3.0 detected in core library",
        "tech_debt": "low",
        "license": "GPL-3.0",
        "patch_needed": False,
    }))])
    ctx = _make_ctx_ma(
        llm,
        file_uris={"code.py": f"local://{doc.as_posix()}"},
        routing={"CodeAgent": ["code.py"]},
        ma_scope={"enterprise_value_usd": 50_000_000},
    )
    findings = await agent.run(ctx)
    # Expect one code-risk Finding + one oss-license deal-stopper
    oss_findings = [f for f in findings if f.category == "oss-license"]
    assert len(oss_findings) == 1
    oss = oss_findings[0]
    assert oss.ic_decision == "deal-stopper"
    assert oss.severity == "critical"
    assert oss.workstream == "tech"
    assert oss.exposure_usd_range == (0, 50_000_000)


async def test_lgpl_in_ma_mode_emits_spa_protection(tmp_path: Path) -> None:
    doc = tmp_path / "code.py"
    doc.write_text("x")
    agent = CodeAgent(model="gemini-2.5-flash")
    llm = ScriptedLLM([LLMResponse(content=json.dumps({
        "summary": "LGPL component identified",
        "tech_debt": "medium",
        "license": "LGPL-2.1",
        "patch_needed": False,
    }))])
    ctx = _make_ctx_ma(
        llm,
        file_uris={"code.py": f"local://{doc.as_posix()}"},
        routing={"CodeAgent": ["code.py"]},
    )
    findings = await agent.run(ctx)
    oss = [f for f in findings if f.category == "oss-license"]
    assert len(oss) == 1
    assert oss[0].ic_decision == "SPA-protection"
    assert oss[0].severity == "high"


async def test_mit_in_ma_mode_emits_no_oss_finding(tmp_path: Path) -> None:
    """Permissive licenses in the allowlist (MIT/Apache/BSD/ISC) → no oss-license Finding."""
    doc = tmp_path / "code.py"
    doc.write_text("x")
    agent = CodeAgent(model="gemini-2.5-flash")
    llm = ScriptedLLM([LLMResponse(content=json.dumps({
        "summary": "Clean code",
        "tech_debt": "low",
        "license": "MIT",
        "patch_needed": False,
    }))])
    ctx = _make_ctx_ma(
        llm,
        file_uris={"code.py": f"local://{doc.as_posix()}"},
        routing={"CodeAgent": ["code.py"]},
    )
    findings = await agent.run(ctx)
    oss = [f for f in findings if f.category == "oss-license"]
    assert oss == []  # MIT is on the allowlist
    # But the base code-risk Finding must still exist
    code_risk = [f for f in findings if f.category == "code-risk"]
    assert len(code_risk) == 1


async def test_vendor_mode_skips_oss_pass(tmp_path: Path) -> None:
    """In vendor mode, OSS license pass is gated out — only the code-risk Finding remains."""
    doc = tmp_path / "code.py"
    doc.write_text("x")
    agent = CodeAgent(model="gemini-2.5-flash")
    llm = ScriptedLLM([LLMResponse(content=json.dumps({
        "summary": "GPL detected",
        "tech_debt": "low",
        "license": "GPL-3.0",
        "patch_needed": False,
    }))])
    ctx = _make_ctx_vendor(
        llm,
        file_uris={"code.py": f"local://{doc.as_posix()}"},
        routing={"CodeAgent": ["code.py"]},
    )
    findings = await agent.run(ctx)
    oss = [f for f in findings if f.category == "oss-license"]
    assert oss == []  # vendor mode never emits oss-license findings
    code_risk = [f for f in findings if f.category == "code-risk"]
    assert len(code_risk) == 1
