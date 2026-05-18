# Risk Scoring + Remediation + ESG Agents — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the three originality differentiator agents (Risk Scoring, Remediation, ESG) per delta-design `docs/superpowers/specs/2026-05-18-three-agents-delta-design.md`, with full Dashboard integration and re-captured replay JSONLs, in time for the 2026-05-19 06:00 SGT submission target.

**Architecture:** Risk Scoring is a deterministic-math-plus-LLM-rationale node inserted between specialists-join and policy. Remediation is a post-policy LLM agent gated by a skip predicate that short-circuits when verdict is approve/proceed with no ≥medium findings. ESG is a 7th specialist mirroring `LegalAgent` shape, enabled in both modes. New Pydantic models (`RiskScore`, `RemediationPlan`, `RemediationItem`, `RiskDriver`) extend `schemas.py`; `TPRMState` gains two new fields. Coordinator templates and React dashboard get two new sections each.

**Tech Stack:** Python 3.11+, Pydantic v2, `orchestra.core.graph.WorkflowGraph`, Gemini 2.5 Flash, React 18 + TypeScript, CSS-only charts (no chart library), pytest with `orchestra.testing.ScriptedLLM`.

---

## File map

**New files:**

```
src/orchestra_tprm/agents/risk_score.py          # RiskScoreAgent (post-join, fail-soft LLM)
src/orchestra_tprm/agents/remediation.py         # RemediationAgent + should_run predicate
src/orchestra_tprm/agents/specialists/esg.py     # ESGAgent (7th specialist)
tests/tprm/unit/test_risk_score_agent.py
tests/tprm/unit/test_remediation_agent.py
tests/tprm/unit/test_esg_agent.py
dashboard/src/components/RiskScoreHero.tsx
dashboard/src/components/RemediationRoadmap.tsx
```

**Modified files:**

```
src/orchestra_tprm/schemas.py                    # +4 models, +2 TPRMState fields
src/orchestra_tprm/graph.py                      # wire risk_score + remediation nodes
src/orchestra_tprm/agents/router.py              # extend kind taxonomy with esg-* tags
src/orchestra_tprm/agents/specialists/__init__.py  # export ESGAgent
src/orchestra_tprm/modes/vendor.yaml             # +esg: gemini-2.5-flash
src/orchestra_tprm/modes/ma.yaml                 # +esg: gemini-2.5-flash
src/orchestra_tprm/policies/vendor.yaml          # +risk_score_thresholds, +esg critical_categories
src/orchestra_tprm/policies/ma.yaml              # +risk_score_thresholds, +esg critical_categories
src/orchestra_tprm/templates/coordinator_vendor.tmpl  # +risk_score + remediation sections
src/orchestra_tprm/templates/coordinator_ma.tmpl      # +risk_score + remediation sections
dashboard/src/App.tsx                            # mount new components, fetch new state fields
tests/tprm/unit/test_graph_wiring.py             # if exists, assert new node order; else add
```

**Re-captured (after agents land):**

```
examples/tprm/hashicorp/replay.jsonl             # new (didn't exist)
examples/tprm/acme/replay.jsonl                  # overwrite stale recording
```

---

### Task 1: Schemas — add 4 models + 2 TPRMState fields

**Files:**
- Modify: `src/orchestra_tprm/schemas.py`
- Test: `tests/tprm/unit/test_schemas_new_models.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/tprm/unit/test_schemas_new_models.py
"""Unit tests for the new Pydantic models added for the 3-agent delta."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestra_tprm.schemas import (
    Finding,
    RemediationItem,
    RemediationPlan,
    RiskDriver,
    RiskScore,
)


def test_risk_driver_round_trip() -> None:
    d = RiskDriver(
        dimension="security",
        finding_id="abc123",
        severity="high",
        one_liner="SOC2 CC6.1 evidence missing.",
    )
    assert d.model_dump()["dimension"] == "security"
    assert d.severity == "high"


def test_risk_score_clamps_verdict_literal() -> None:
    r = RiskScore(
        overall=42,
        verdict="amber",
        dimensions={"security": 60, "legal": 20},
        top_risk_drivers=[],
        explanation="Mixed risk.",
    )
    assert r.overall == 42
    assert r.verdict == "amber"

    with pytest.raises(ValidationError):
        RiskScore(
            overall=42, verdict="bogus", dimensions={}, top_risk_drivers=[], explanation=""
        )


def test_remediation_item_priority_validates() -> None:
    item = RemediationItem(
        finding_id="abc",
        action="Demand SOC2 Type II report",
        owner="vendor",
        priority="P0",
        leverage="MSA section 14.2 — security warranty",
    )
    assert item.priority == "P0"

    with pytest.raises(ValidationError):
        RemediationItem(
            finding_id="x",
            action="x",
            owner="vendor",
            priority="P9",
            leverage="x",
        )


def test_remediation_plan_defaults_horizon_zero() -> None:
    plan = RemediationPlan(items=[], horizon_days=0, summary="No remediation required.")
    assert plan.horizon_days == 0
    assert plan.items == []


def test_finding_id_factory_unique() -> None:
    a = Finding(agent="legal", category="x", severity="low", summary="a")
    b = Finding(agent="legal", category="x", severity="low", summary="b")
    assert a.id != b.id
    assert len(a.id) == 32  # uuid4 hex length without dashes — confirm in schema
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/test_schemas_new_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'RiskScore' from 'orchestra_tprm.schemas'`

- [ ] **Step 3: Inspect current `Finding.id` factory**

Run: `grep -n 'id: str' src/orchestra_tprm/schemas.py`
Expected output includes: `id: str = Field(default_factory=lambda: str(uuid.uuid4()))`

If the factory uses `str(uuid.uuid4())` (with dashes, length 36), update the test's length assertion to `36`. If it uses `uuid.uuid4().hex` (length 32), keep as-is.

- [ ] **Step 4: Add the 4 new models + 2 TPRMState fields**

Append after the existing `Finding`, `MAScope`, `ICMemo` definitions in `src/orchestra_tprm/schemas.py`:

```python
class RiskDriver(BaseModel):
    dimension: str
    finding_id: str
    severity: SeverityLiteral
    one_liner: str


class RiskScore(BaseModel):
    overall: int = Field(ge=0, le=100)
    verdict: Literal["green", "amber", "red"]
    dimensions: dict[str, int] = Field(default_factory=dict)
    top_risk_drivers: list[RiskDriver] = Field(default_factory=list)
    explanation: str = ""


class RemediationItem(BaseModel):
    finding_id: str
    action: str
    owner: Literal["vendor", "buyer", "both"]
    priority: Literal["P0", "P1", "P2"]
    leverage: str
    est_effort_days: int | None = None


class RemediationPlan(BaseModel):
    items: list[RemediationItem] = Field(default_factory=list)
    horizon_days: int = 0
    summary: str = ""
```

In the existing `class TPRMState(WorkflowState):` block, add (alphabetised with existing fields):

```python
    risk_score: RiskScore | None
    remediation_plan: RemediationPlan | None
```

If `TPRMState` is a `TypedDict` rather than a class, the same two annotations apply.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/test_schemas_new_models.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Run the full schema test family to confirm no regression**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/ -k 'schema' -v`
Expected: All existing schema tests still pass.

- [ ] **Step 7: Commit**

```bash
cd Orchestra
git add src/orchestra_tprm/schemas.py tests/tprm/unit/test_schemas_new_models.py
git commit -m "feat(schemas): add RiskScore, RemediationPlan + TPRMState fields"
```

---

### Task 2: ESG specialist agent

**Files:**
- Create: `src/orchestra_tprm/agents/specialists/esg.py`
- Modify: `src/orchestra_tprm/agents/specialists/__init__.py`
- Test: `tests/tprm/unit/test_esg_agent.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/test_esg_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'orchestra_tprm.agents.specialists.esg'`

- [ ] **Step 3: Write the ESGAgent implementation**

Create `src/orchestra_tprm/agents/specialists/esg.py`:

```python
"""ESGAgent — 7th specialist for ESG disclosure review.

Reviews vendor's ESG disclosures (sustainability report, governance docs,
diversity report, supplier code of conduct) and emits findings against the
Environmental / Social / Governance checklist defined in the system prompt.

Active in both vendor and M&A modes.
"""
from __future__ import annotations

import json

from orchestra.core.context import ExecutionContext

from orchestra_tprm.agents._uri import read_uri
from orchestra_tprm.agents.base import BaseTPRMAgent, strip_json_fences
from orchestra_tprm.schemas import Citation, Finding

_SYSTEM = """You are an ESG (Environmental, Social, Governance) compliance analyst.
For each gap or risk you identify, output one JSON object with these fields:
  - category: short slug from the controlled vocabulary below
  - severity: "low" | "medium" | "high" | "critical"
  - summary: one sentence describing the gap
  - citation_page: integer page number, or null

Controlled categories:
Environmental:
  - "net-zero-commitment" (critical if no target year disclosed)
  - "scope-emissions-disclosure" (high if Scope 3 missing, medium if Scope 1+2 only)
  - "renewable-energy-mix" (low-medium)
  - "e-waste-policy" (low-medium)
Social:
  - "dei-metrics" (medium-high)
  - "supply-chain-labour-audit" (medium-high)
  - "modern-slavery-statement" (high if missing, critical if non-compliant w/ MSA 2015)
  - "customer-privacy-framework" (medium)
Governance:
  - "board-independence" (medium-high)
  - "audit-committee" (medium)
  - "anti-corruption-policy" (high if missing, critical if known violation)
  - "whistleblower-protection" (medium)
  - "security-audit-cadence" (medium-high)

Output a JSON ARRAY of objects. No prose, no Markdown.
If documents fully disclose against this checklist with no gaps, return [].
"""


class ESGAgent(BaseTPRMAgent):
    """Reviews ESG disclosure documents and emits per-gap findings."""

    name = "ESGAgent"

    def __init__(self, model: str = "gemini-2.5-flash") -> None:
        self.model = model

    async def _emit_findings(self, ctx: ExecutionContext) -> list[Finding]:
        file_uris: dict[str, str] = ctx.state.get("file_uris", {})
        routing: dict[str, list[str]] = ctx.state.get("routing", {})
        my_docs = routing.get(self.name, [])

        if not my_docs:
            return [
                Finding(
                    agent=self.name,
                    category="esg-no-docs",
                    severity="low",
                    summary=(
                        "No ESG disclosure documents were routed to ESGAgent — "
                        "ESG posture could not be assessed."
                    ),
                )
            ]

        all_findings: list[Finding] = []
        for doc_id in my_docs:
            uri = file_uris.get(doc_id)
            if not uri:
                continue
            attachments = None
            try:
                content = read_uri(uri)
            except (FileNotFoundError, OSError, UnicodeDecodeError):
                content = ""
            if not content:
                continue
            body = content

            prompt = (
                f"Subject: {ctx.state.get('subject_name', 'unknown')}\n"
                f"Document: {doc_id}\n"
                f"{body}\n"
                "Review the document above against the ESG checklist. "
                "Output the JSON array as instructed."
            )

            text = await self._call_llm(
                ctx, prompt=prompt, system=_SYSTEM, attachments=attachments
            )
            if not text.strip():
                continue

            try:
                items = json.loads(strip_json_fences(text))
            except json.JSONDecodeError:
                all_findings.append(
                    Finding(
                        agent=self.name,
                        category="parse-error",
                        severity="high",
                        summary=f"ESGAgent: LLM returned non-JSON for {doc_id}: {text[:120]}",
                        evidence=[Citation(file_id=doc_id)],
                    )
                )
                continue

            for item in items:
                page = item.get("citation_page")
                all_findings.append(
                    Finding(
                        agent=self.name,
                        category=item.get("category", "unspecified"),
                        severity=item.get("severity", "medium"),
                        summary=item.get("summary", ""),
                        evidence=[
                            Citation(
                                file_id=doc_id,
                                page=int(page) if page is not None else None,
                            )
                        ],
                    )
                )

        return all_findings
```

- [ ] **Step 4: Export ESGAgent from the specialists package**

Modify `src/orchestra_tprm/agents/specialists/__init__.py`. Add to the imports + `__all__`:

```python
from orchestra_tprm.agents.specialists.esg import ESGAgent

__all__ = [
    # ...existing...
    "ESGAgent",
]
```

(Inspect the file first; the exact `__all__` location may vary. If `__all__` is absent, just add the import line.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/test_esg_agent.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Confirm no existing specialist tests broke**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/ -k 'agent' -v`
Expected: All previous specialist agent tests still pass.

- [ ] **Step 7: Commit**

```bash
cd Orchestra
git add src/orchestra_tprm/agents/specialists/esg.py \
        src/orchestra_tprm/agents/specialists/__init__.py \
        tests/tprm/unit/test_esg_agent.py
git commit -m "feat(esg): add ESGAgent as 7th specialist for both modes"
```

---

### Task 3: Wire ESG into mode YAMLs, policy YAMLs, and router

**Files:**
- Modify: `src/orchestra_tprm/modes/vendor.yaml`
- Modify: `src/orchestra_tprm/modes/ma.yaml`
- Modify: `src/orchestra_tprm/policies/vendor.yaml`
- Modify: `src/orchestra_tprm/policies/ma.yaml`
- Modify: `src/orchestra_tprm/agents/router.py`
- Test: `tests/tprm/unit/test_esg_wiring.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/tprm/unit/test_esg_wiring.py
"""Verify ESG is wired into both modes' configs and policy packs."""
from __future__ import annotations

from pathlib import Path

import yaml


_MODES = Path(__file__).resolve().parents[3] / "src" / "orchestra_tprm" / "modes"
_POLICIES = Path(__file__).resolve().parents[3] / "src" / "orchestra_tprm" / "policies"


def test_vendor_mode_has_esg_specialist() -> None:
    cfg = yaml.safe_load((_MODES / "vendor.yaml").read_text(encoding="utf-8"))
    assert "esg" in cfg["specialists"]
    assert cfg["specialists"]["esg"] == "gemini-2.5-flash"


def test_ma_mode_has_esg_specialist() -> None:
    cfg = yaml.safe_load((_MODES / "ma.yaml").read_text(encoding="utf-8"))
    assert "esg" in cfg["specialists"]
    assert cfg["specialists"]["esg"] == "gemini-2.5-flash"


def test_vendor_policy_has_esg_critical_categories() -> None:
    policy = yaml.safe_load((_POLICIES / "vendor.yaml").read_text(encoding="utf-8"))
    crits = policy.get("critical_categories", [])
    assert "net-zero-commitment" in crits
    assert "modern-slavery-statement" in crits
    assert "anti-corruption-policy" in crits


def test_ma_policy_has_esg_critical_categories() -> None:
    policy = yaml.safe_load((_POLICIES / "ma.yaml").read_text(encoding="utf-8"))
    crits = policy.get("critical_categories", [])
    assert "net-zero-commitment" in crits
    assert "modern-slavery-statement" in crits
    assert "anti-corruption-policy" in crits
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/test_esg_wiring.py -v`
Expected: FAIL — `assert 'esg' in cfg['specialists']`

- [ ] **Step 3: Add `esg` to vendor mode YAML**

In `src/orchestra_tprm/modes/vendor.yaml`, append under `specialists:`:

```yaml
specialists:
  legal: gemini-2.5-flash
  financial: null
  security: gemini-2.5-flash
  code: gemini-2.5-flash
  external: gemini-2.5-flash
  esg: gemini-2.5-flash
```

- [ ] **Step 4: Add `esg` to M&A mode YAML**

In `src/orchestra_tprm/modes/ma.yaml`, append under `specialists:`:

```yaml
specialists:
  legal: gemini-2.5-flash
  financial: gemini-2.5-flash
  security: gemini-2.5-flash
  code: gemini-2.5-flash
  external: gemini-2.5-flash
  saas_metrics: gemini-2.5-pro
  esg: gemini-2.5-flash
```

- [ ] **Step 5: Read current policy YAML structure**

Run: `cd Orchestra && cat src/orchestra_tprm/policies/vendor.yaml`
Note: locate the existing `critical_categories:` block (or `weights:` if `critical_categories` doesn't exist yet — in that case, add it as a top-level key).

- [ ] **Step 6: Add ESG critical categories to both policy YAMLs**

In each of `src/orchestra_tprm/policies/vendor.yaml` and `src/orchestra_tprm/policies/ma.yaml`, locate `critical_categories:` (or add it if missing) and append:

```yaml
critical_categories:
  # ...existing entries preserved...
  - net-zero-commitment
  - modern-slavery-statement
  - anti-corruption-policy
```

- [ ] **Step 7: Extend router kind taxonomy for ESG documents**

In `src/orchestra_tprm/agents/router.py`, locate the kind-to-specialist mapping (look for `_KIND_TO_AGENT_NAMES` or the LLM prompt enumerating document kinds). Add four new kinds routing to `ESGAgent`:

```python
# In _KIND_TO_AGENT_NAMES (or equivalent):
"sustainability-report": ["ESGAgent"],
"code-of-conduct":       ["ESGAgent"],
"diversity-report":      ["ESGAgent"],
"governance-disclosure": ["ESGAgent"],
```

If the router uses a prompt-only classification (no static map), extend the LLM system prompt's kind enumeration to include those four kinds and instruct the LLM to route them to `ESGAgent`.

- [ ] **Step 8: Run test to verify it passes**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/test_esg_wiring.py -v`
Expected: PASS (4 tests)

- [ ] **Step 9: Confirm router tests still green**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/ -k 'router' -v`
Expected: All previous router tests still pass.

- [ ] **Step 10: Commit**

```bash
cd Orchestra
git add src/orchestra_tprm/modes/vendor.yaml \
        src/orchestra_tprm/modes/ma.yaml \
        src/orchestra_tprm/policies/vendor.yaml \
        src/orchestra_tprm/policies/ma.yaml \
        src/orchestra_tprm/agents/router.py \
        tests/tprm/unit/test_esg_wiring.py
git commit -m "feat(esg): wire ESG specialist into modes, policies, router"
```

---

### Task 4: RiskScoreAgent — deterministic math + LLM rationale + fallback

**Files:**
- Create: `src/orchestra_tprm/agents/risk_score.py`
- Modify: `src/orchestra_tprm/policies/vendor.yaml` (add `risk_score_thresholds`)
- Modify: `src/orchestra_tprm/policies/ma.yaml` (add `risk_score_thresholds`)
- Test: `tests/tprm/unit/test_risk_score_agent.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tprm/unit/test_risk_score_agent.py
"""Unit tests for RiskScoreAgent: deterministic math + LLM rationale + fallback."""
from __future__ import annotations

import json

import pytest

from orchestra.core.context import ExecutionContext
from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM

from orchestra_tprm.agents.risk_score import RiskScoreAgent
from orchestra_tprm.schemas import Finding


_POLICY = {
    "weights": {"low": 1, "medium": 3, "high": 7, "critical": 15},
    "risk_score_thresholds": {"green_max": 30, "amber_max": 69},
}


def _ctx(provider, *, findings):
    ctx = ExecutionContext(provider=provider)
    ctx.state = {"findings": findings, "subject_name": "HashiCorp"}
    return ctx


async def test_empty_findings_yields_zero_green() -> None:
    llm = ScriptedLLM([])  # never invoked because no drivers
    agent = RiskScoreAgent(policy=_POLICY, model="gemini-2.5-flash")
    ctx = _ctx(llm, findings=[])
    result = await agent.run(ctx)
    rs = result["risk_score"]
    assert rs.overall == 0
    assert rs.verdict == "green"
    assert rs.top_risk_drivers == []


async def test_all_critical_yields_high_score_red() -> None:
    findings = [
        Finding(agent="security", category="x", severity="critical", summary="s")
        for _ in range(3)
    ]
    llm = ScriptedLLM([LLMResponse(content=json.dumps({
        "explanation": "All three critical security gaps.",
        "driver_one_liners": ["A", "B", "C"],
    }))])
    agent = RiskScoreAgent(policy=_POLICY, model="gemini-2.5-flash")
    result = await agent.run(_ctx(llm, findings=findings))
    rs = result["risk_score"]
    assert rs.overall == 100
    assert rs.verdict == "red"
    assert len(rs.top_risk_drivers) == 3
    assert rs.top_risk_drivers[0].one_liner == "A"


async def test_mixed_severities_math_correct() -> None:
    # weights: low=1, medium=3, high=7, critical=15 → max possible = 4 * 15 = 60
    # sum = 1 + 3 + 7 + 15 = 26 → 100*26/60 = 43 → amber
    findings = [
        Finding(agent="legal",    category="a", severity="low",      summary="a"),
        Finding(agent="security", category="b", severity="medium",   summary="b"),
        Finding(agent="code",     category="c", severity="high",     summary="c"),
        Finding(agent="esg",      category="d", severity="critical", summary="d"),
    ]
    llm = ScriptedLLM([LLMResponse(content=json.dumps({
        "explanation": "Mixed risk profile.",
        "driver_one_liners": ["esg crit", "code high", "sec medium"],
    }))])
    agent = RiskScoreAgent(policy=_POLICY, model="gemini-2.5-flash")
    result = await agent.run(_ctx(llm, findings=findings))
    rs = result["risk_score"]
    assert rs.overall == 43
    assert rs.verdict == "amber"
    assert set(rs.dimensions.keys()) == {"legal", "security", "code", "esg"}
    # Per-dimension: each has 1 finding; dim score = 100 * weight / (1 * 15)
    assert rs.dimensions["esg"] == 100  # critical / critical
    assert rs.dimensions["legal"] == round(100 * 1 / 15)


async def test_llm_failure_uses_fallback_explanation() -> None:
    # ScriptedLLM with empty queue raises when called → agent must catch and fall back.
    findings = [
        Finding(agent="security", category="x", severity="high", summary="SOC2 gap"),
    ]
    llm = ScriptedLLM([])  # no responses queued — raises on first call
    agent = RiskScoreAgent(policy=_POLICY, model="gemini-2.5-flash")
    result = await agent.run(_ctx(llm, findings=findings))
    rs = result["risk_score"]
    assert rs.overall > 0
    # Fallback explanation references the top dimension
    assert "security" in rs.explanation.lower()
    assert rs.top_risk_drivers[0].one_liner.startswith("SOC2 gap")


async def test_verdict_thresholds_match_policy() -> None:
    # 30 overall = green (≤ green_max)
    # 31 overall = amber
    # 70 overall = red (≥ amber_max + 1)
    agent = RiskScoreAgent(policy=_POLICY, model="gemini-2.5-flash")
    assert agent._verdict(30) == "green"
    assert agent._verdict(31) == "amber"
    assert agent._verdict(69) == "amber"
    assert agent._verdict(70) == "red"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/test_risk_score_agent.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Add `risk_score_thresholds` to both policy YAMLs**

In `src/orchestra_tprm/policies/vendor.yaml`, add at the top level:

```yaml
risk_score_thresholds:
  green_max: 30
  amber_max: 69
```

In `src/orchestra_tprm/policies/ma.yaml`, add at the top level:

```yaml
risk_score_thresholds:
  green_max: 20
  amber_max: 59
```

- [ ] **Step 4: Write the RiskScoreAgent implementation**

Create `src/orchestra_tprm/agents/risk_score.py`:

```python
"""RiskScoreAgent — deterministic math + LLM rationale + fail-soft fallback.

Position: between specialists-join and policy.

Math is computed in Python; the LLM is used only to produce the explanation
string and the three driver one-liners. If the LLM call fails (quota, safety,
network), the agent falls back to template strings derived from finding
metadata so the demo never crashes.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from orchestra.core.context import ExecutionContext

from orchestra_tprm.agents.base import strip_json_fences
from orchestra_tprm.schemas import Finding, RiskDriver, RiskScore

logger = logging.getLogger(__name__)

_SYSTEM = """You are a vendor risk analyst. Given a list of risk findings, write:
  - "explanation": a 1-2 sentence summary of the risk profile
  - "driver_one_liners": exactly N short sentences (≤ 20 words each), one per driver, in order

Output a single JSON object. No prose, no Markdown.
"""


class RiskScoreAgent:
    """Computes 0-100 risk score + verdict + per-dimension breakdown.

    Public surface:
      __call__(state, *, ctx) -> {"risk_score": RiskScore}

    Plain callable (not BaseTPRMAgent) because it does not emit Findings.
    """

    name = "RiskScoreAgent"

    def __init__(self, *, policy: dict[str, Any], model: str = "gemini-2.5-flash") -> None:
        self._weights: dict[str, int] = policy.get("weights", {
            "low": 1, "medium": 3, "high": 7, "critical": 15,
        })
        thresholds = policy.get("risk_score_thresholds", {"green_max": 30, "amber_max": 69})
        self._green_max = int(thresholds["green_max"])
        self._amber_max = int(thresholds["amber_max"])
        self.model = model

    async def run(self, ctx: ExecutionContext) -> dict[str, Any]:
        """Convenience wrapper for direct invocation (mirrors specialist agents)."""
        return await self.__call__(ctx.state, ctx=ctx)

    async def __call__(
        self, state: dict[str, Any], *, ctx: ExecutionContext | None = None
    ) -> dict[str, Any]:
        findings = self._coerce_findings(state.get("findings", []))

        if not findings:
            return {
                "risk_score": RiskScore(
                    overall=0,
                    verdict="green",
                    dimensions={},
                    top_risk_drivers=[],
                    explanation="No findings emitted by specialists.",
                )
            }

        overall = self._score(findings)
        verdict = self._verdict(overall)
        dimensions = self._dimensions(findings)
        drivers_findings = self._top_drivers(findings, n=3)

        # Build driver shells with empty one-liners (LLM fills these)
        driver_shells = [
            RiskDriver(
                dimension=f.agent.replace("Agent", "").lower(),
                finding_id=f.id,
                severity=f.severity,
                one_liner="",
            )
            for f in drivers_findings
        ]

        explanation, one_liners = await self._narrate(ctx, drivers_findings, dimensions)

        # Stitch one-liners into the driver shells, with fallback
        for i, d in enumerate(driver_shells):
            d.one_liner = one_liners[i] if i < len(one_liners) and one_liners[i] else (
                drivers_findings[i].summary[:120]
            )

        return {
            "risk_score": RiskScore(
                overall=overall,
                verdict=verdict,
                dimensions=dimensions,
                top_risk_drivers=driver_shells,
                explanation=explanation,
            )
        }

    def _verdict(self, overall: int) -> str:
        if overall <= self._green_max:
            return "green"
        if overall <= self._amber_max:
            return "amber"
        return "red"

    def _score(self, findings: list[Finding]) -> int:
        weighted = sum(self._weights.get(f.severity, 0) for f in findings)
        max_possible = max(len(findings), 1) * self._weights.get("critical", 15)
        overall = round(100 * weighted / max_possible)
        return min(100, max(0, overall))

    def _dimensions(self, findings: list[Finding]) -> dict[str, int]:
        out: dict[str, int] = {}
        by_agent: dict[str, list[Finding]] = {}
        for f in findings:
            key = f.agent.replace("Agent", "").lower()
            by_agent.setdefault(key, []).append(f)
        for dim, items in by_agent.items():
            out[dim] = self._score(items)
        return out

    def _top_drivers(self, findings: list[Finding], *, n: int) -> list[Finding]:
        return sorted(findings, key=lambda f: -self._weights.get(f.severity, 0))[:n]

    async def _narrate(
        self,
        ctx: ExecutionContext | None,
        drivers: list[Finding],
        dimensions: dict[str, int],
    ) -> tuple[str, list[str]]:
        """LLM call with fail-soft fallback."""
        if ctx is None or not drivers:
            return self._fallback(dimensions, drivers)

        prompt_payload = {
            "drivers": [
                {"dim": f.agent, "severity": f.severity, "summary": f.summary}
                for f in drivers
            ],
            "dimensions": dimensions,
        }
        prompt = f"Findings:\n{json.dumps(prompt_payload, indent=2)}\nReturn the JSON object."

        try:
            from orchestra.core.types import Message, MessageRole
            messages = [
                Message(role=MessageRole.SYSTEM, content=_SYSTEM),
                Message(role=MessageRole.USER, content=prompt),
            ]
            resp = await ctx.provider.complete(messages=messages, model=self.model)
            text = strip_json_fences(resp.content if hasattr(resp, "content") else str(resp))
            obj = json.loads(text)
            explanation = str(obj.get("explanation", "")).strip()
            one_liners = [str(s) for s in obj.get("driver_one_liners", [])]
            if not explanation or not one_liners:
                raise ValueError("LLM response missing required fields")
            return explanation, one_liners
        except Exception as exc:  # noqa: BLE001 — intentional broad catch for fail-soft
            logger.warning("RiskScoreAgent LLM call failed (%s), using fallback", exc)
            return self._fallback(dimensions, drivers)

    def _fallback(
        self, dimensions: dict[str, int], drivers: list[Finding]
    ) -> tuple[str, list[str]]:
        top_dims = sorted(dimensions.items(), key=lambda kv: -kv[1])[:2]
        if top_dims:
            dims_str = ", ".join(name for name, _ in top_dims)
            explanation = f"Risk concentrated in {dims_str}."
        else:
            explanation = "Risk profile not narratable."
        one_liners = [f.summary[:120] for f in drivers]
        return explanation, one_liners

    @staticmethod
    def _coerce_findings(raw: list[Any]) -> list[Finding]:
        return [f if isinstance(f, Finding) else Finding(**f) for f in raw]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/test_risk_score_agent.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
cd Orchestra
git add src/orchestra_tprm/agents/risk_score.py \
        src/orchestra_tprm/policies/vendor.yaml \
        src/orchestra_tprm/policies/ma.yaml \
        tests/tprm/unit/test_risk_score_agent.py
git commit -m "feat(risk-score): deterministic math + LLM rationale agent"
```

---

### Task 5: RemediationAgent — mode-aware + skip gate

**Files:**
- Create: `src/orchestra_tprm/agents/remediation.py`
- Test: `tests/tprm/unit/test_remediation_agent.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tprm/unit/test_remediation_agent.py
"""Unit tests for RemediationAgent: skip predicate + mode-aware prompt."""
from __future__ import annotations

import json

from orchestra.core.context import ExecutionContext
from orchestra.core.types import LLMResponse
from orchestra.testing import ScriptedLLM

from orchestra_tprm.agents.remediation import RemediationAgent, should_run_remediation
from orchestra_tprm.schemas import Finding


def _ctx(provider, *, findings, verdict, ic_recommendation=None):
    ctx = ExecutionContext(provider=provider)
    ctx.state = {
        "findings": findings,
        "policy_verdict": verdict,
        "ic_memo": {"recommendation": ic_recommendation} if ic_recommendation else {},
        "subject_name": "HashiCorp",
    }
    return ctx


def test_skip_when_approve_and_no_medium_plus() -> None:
    findings = [Finding(agent="legal", category="x", severity="low", summary="trivial")]
    state = {"findings": findings, "policy_verdict": "approve", "ic_memo": {}}
    assert should_run_remediation(state) is False


def test_run_when_approve_but_has_medium() -> None:
    findings = [Finding(agent="legal", category="x", severity="medium", summary="m")]
    state = {"findings": findings, "policy_verdict": "approve", "ic_memo": {}}
    assert should_run_remediation(state) is True


def test_run_when_reject_verdict() -> None:
    state = {"findings": [], "policy_verdict": "reject", "ic_memo": {}}
    assert should_run_remediation(state) is True


def test_skip_when_ma_proceed_and_no_medium_plus() -> None:
    state = {
        "findings": [Finding(agent="x", category="x", severity="low", summary="x")],
        "policy_verdict": "",
        "ic_memo": {"recommendation": "proceed"},
    }
    assert should_run_remediation(state) is False


async def test_vendor_framing_generates_vendor_owner_items() -> None:
    findings = [
        Finding(agent="security", category="soc2-gap", severity="high", summary="SOC2 missing"),
    ]
    llm = ScriptedLLM([LLMResponse(content=json.dumps({
        "items": [
            {
                "finding_id": findings[0].id,
                "action": "Demand SOC2 Type II report before signing",
                "owner": "vendor",
                "priority": "P0",
                "leverage": "MSA security warranty clause",
                "est_effort_days": 30,
            }
        ],
        "horizon_days": 30,
        "summary": "Vendor must close SOC2 gap before contract execution.",
    }))])
    agent = RemediationAgent(mode="vendor", model="gemini-2.5-flash")
    ctx = _ctx(llm, findings=findings, verdict="conditional-approve")
    result = await agent.run(ctx)
    plan = result["remediation_plan"]
    assert len(plan.items) == 1
    assert plan.items[0].owner == "vendor"
    assert plan.items[0].priority == "P0"
    assert plan.horizon_days == 30


async def test_ma_framing_generates_buyer_owner_items() -> None:
    findings = [
        Finding(agent="legal", category="ip-assignment", severity="high", summary="IP gap"),
    ]
    llm = ScriptedLLM([LLMResponse(content=json.dumps({
        "items": [
            {
                "finding_id": findings[0].id,
                "action": "Negotiate IP-rep indemnity with 18-month survival",
                "owner": "buyer",
                "priority": "P1",
                "leverage": "SPA section 8.2 reps & warranties",
                "est_effort_days": 60,
            }
        ],
        "horizon_days": 60,
        "summary": "Address IP gap via SPA reps and indemnity.",
    }))])
    agent = RemediationAgent(mode="ma", model="gemini-2.5-flash")
    ctx = _ctx(llm, findings=findings, verdict="", ic_recommendation="reprice")
    result = await agent.run(ctx)
    plan = result["remediation_plan"]
    assert plan.items[0].owner == "buyer"


async def test_skip_emits_empty_plan_with_summary() -> None:
    findings = [Finding(agent="legal", category="x", severity="low", summary="ok")]
    llm = ScriptedLLM([])  # never called when skipped
    agent = RemediationAgent(mode="vendor", model="gemini-2.5-flash")
    ctx = _ctx(llm, findings=findings, verdict="approve")
    result = await agent.run(ctx)
    plan = result["remediation_plan"]
    assert plan.items == []
    assert "clean" in plan.summary.lower()


async def test_llm_parse_error_returns_empty_plan() -> None:
    findings = [Finding(agent="security", category="x", severity="high", summary="bad")]
    llm = ScriptedLLM([LLMResponse(content="not-json-at-all")])
    agent = RemediationAgent(mode="vendor", model="gemini-2.5-flash")
    ctx = _ctx(llm, findings=findings, verdict="conditional-approve")
    result = await agent.run(ctx)
    plan = result["remediation_plan"]
    assert plan.items == []
    assert "parse" in plan.summary.lower() or "unavailable" in plan.summary.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/test_remediation_agent.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the RemediationAgent implementation**

Create `src/orchestra_tprm/agents/remediation.py`:

```python
"""RemediationAgent — mode-aware action plan generator.

Position: after policy (and after pmi_planner in M&A mode).

Skipped when verdict is approve/proceed and there are no findings of
severity ≥ medium. When skipped, emits an empty RemediationPlan so the
downstream rendering pipeline always has something to consume.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from orchestra.core.context import ExecutionContext
from orchestra.core.types import Message, MessageRole

from orchestra_tprm.agents.base import strip_json_fences
from orchestra_tprm.schemas import Finding, RemediationItem, RemediationPlan

logger = logging.getLogger(__name__)


def should_run_remediation(state: dict[str, Any]) -> bool:
    """True when remediation is worth generating; False to skip."""
    verdict = state.get("policy_verdict") or ""
    ic_memo = state.get("ic_memo") or {}
    ic_rec = ic_memo.get("recommendation") if isinstance(ic_memo, dict) else None

    findings_raw = state.get("findings", [])
    has_medium_plus = False
    for f in findings_raw:
        sev = f.severity if isinstance(f, Finding) else f.get("severity", "")
        if sev in ("medium", "high", "critical"):
            has_medium_plus = True
            break

    approve_set = {"approve", "proceed"}
    is_approve = verdict in approve_set or ic_rec in approve_set
    return not (is_approve and not has_medium_plus)


_VENDOR_SYSTEM = """You are a vendor-onboarding remediation analyst.
For each finding of severity ≥ medium, write the action the VENDOR must take
before contract signing. Owner is usually "vendor". Leverage refers to a
specific contract clause, certification, or evidence we can demand.

Output a single JSON object:
{
  "items": [
    {
      "finding_id": "<copy from input>",
      "action": "<imperative, specific>",
      "owner": "vendor" | "buyer" | "both",
      "priority": "P0" | "P1" | "P2",
      "leverage": "<contract clause / cert / evidence>",
      "est_effort_days": <int or null>
    }
  ],
  "horizon_days": <int — max est_effort_days across items>,
  "summary": "<1 sentence>"
}
No prose, no Markdown.
"""

_MA_SYSTEM = """You are an M&A deal-structuring analyst.
For each finding of severity ≥ medium, write the action the BUYER can take to
mitigate it via deal terms: price reduction, indemnity, escrow, rep-and-warranty
insurance, or post-close monitoring. Owner is usually "buyer". Leverage refers
to the specific SPA clause, escrow term, or RWI policy.

Output a single JSON object with the same shape as the vendor mode (items[],
horizon_days, summary). No prose, no Markdown.
"""


class RemediationAgent:
    """Generates a prioritized RemediationPlan from findings, mode-aware."""

    name = "RemediationAgent"

    def __init__(self, *, mode: str, model: str = "gemini-2.5-flash") -> None:
        if mode not in ("vendor", "ma"):
            raise ValueError(f"Unknown mode: {mode}")
        self._mode = mode
        self.model = model

    async def run(self, ctx: ExecutionContext) -> dict[str, Any]:
        return await self.__call__(ctx.state, ctx=ctx)

    async def __call__(
        self, state: dict[str, Any], *, ctx: ExecutionContext | None = None
    ) -> dict[str, Any]:
        if not should_run_remediation(state):
            return {
                "remediation_plan": RemediationPlan(
                    items=[],
                    horizon_days=0,
                    summary="No remediation required — clean approval.",
                )
            }

        findings = self._coerce_findings(state.get("findings", []))
        actionable = [f for f in findings if f.severity in ("medium", "high", "critical")]

        if not actionable or ctx is None:
            return {
                "remediation_plan": RemediationPlan(
                    items=[], horizon_days=0,
                    summary="No actionable findings.",
                )
            }

        system_prompt = _VENDOR_SYSTEM if self._mode == "vendor" else _MA_SYSTEM
        payload = [
            {
                "finding_id": f.id,
                "agent": f.agent,
                "category": f.category,
                "severity": f.severity,
                "summary": f.summary,
            }
            for f in actionable
        ]
        prompt = f"Findings to remediate:\n{json.dumps(payload, indent=2)}\nReturn the JSON object."

        try:
            messages = [
                Message(role=MessageRole.SYSTEM, content=system_prompt),
                Message(role=MessageRole.USER, content=prompt),
            ]
            resp = await ctx.provider.complete(messages=messages, model=self.model)
            text = strip_json_fences(resp.content if hasattr(resp, "content") else str(resp))
            obj = json.loads(text)
        except (json.JSONDecodeError, Exception) as exc:  # noqa: BLE001
            logger.warning("RemediationAgent LLM/parse failed (%s)", exc)
            return {
                "remediation_plan": RemediationPlan(
                    items=[], horizon_days=0,
                    summary="Remediation plan unavailable — parse error or LLM timeout.",
                )
            }

        items_raw = obj.get("items", [])
        items: list[RemediationItem] = []
        for raw in items_raw:
            try:
                items.append(RemediationItem(**raw))
            except Exception:  # noqa: BLE001
                continue

        horizon = int(obj.get("horizon_days", 0))
        if items and horizon == 0:
            horizon = max((i.est_effort_days or 0) for i in items)

        return {
            "remediation_plan": RemediationPlan(
                items=items,
                horizon_days=horizon,
                summary=str(obj.get("summary", "")),
            )
        }

    @staticmethod
    def _coerce_findings(raw: list[Any]) -> list[Finding]:
        return [f if isinstance(f, Finding) else Finding(**f) for f in raw]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/test_remediation_agent.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
cd Orchestra
git add src/orchestra_tprm/agents/remediation.py \
        tests/tprm/unit/test_remediation_agent.py
git commit -m "feat(remediation): mode-aware action plan with skip gate"
```

---

### Task 6: Wire the new agents into `build_graph`

**Files:**
- Modify: `src/orchestra_tprm/graph.py`
- Test: `tests/tprm/unit/test_graph_wiring_new_agents.py` (new)

- [ ] **Step 1: Read current graph.py structure**

Run: `cd Orchestra && grep -n 'g.add_node\|g.add_edge\|g.add_conditional' src/orchestra_tprm/graph.py | head -40`

Note the node names used for `policy`, `pmi_planner`, `coordinator` and any join construct.

- [ ] **Step 2: Write the failing integration test**

```python
# tests/tprm/unit/test_graph_wiring_new_agents.py
"""Verify the new agents are wired into build_graph for both modes."""
from __future__ import annotations

from pathlib import Path

import yaml

from orchestra_tprm.graph import build_graph
from orchestra_tprm.modes.config import ModeConfig


def _adapters_stub():
    """Minimal stub for the Adapters dataclass — implementations not exercised."""
    from types import SimpleNamespace
    return SimpleNamespace(bq=None, sheets=None, docs=None, drive=None, github=None)


def _load_mode(name: str) -> ModeConfig:
    cfg_path = Path(__file__).resolve().parents[3] / "src" / "orchestra_tprm" / "modes" / f"{name}.yaml"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    return ModeConfig(**data)


def test_vendor_graph_has_risk_score_and_remediation_nodes() -> None:
    cfg = _load_mode("vendor")
    g = build_graph(cfg, adapters=_adapters_stub())
    node_names = set(g.nodes.keys()) if hasattr(g, "nodes") else set(g._nodes.keys())
    assert "risk_score" in node_names
    assert "remediation" in node_names or "remediation_gate" in node_names


def test_ma_graph_has_risk_score_and_remediation_nodes() -> None:
    cfg = _load_mode("ma")
    g = build_graph(cfg, adapters=_adapters_stub())
    node_names = set(g.nodes.keys()) if hasattr(g, "nodes") else set(g._nodes.keys())
    assert "risk_score" in node_names
    assert "remediation" in node_names or "remediation_gate" in node_names


def test_vendor_graph_has_esg_specialist() -> None:
    cfg = _load_mode("vendor")
    g = build_graph(cfg, adapters=_adapters_stub())
    node_names = set(g.nodes.keys()) if hasattr(g, "nodes") else set(g._nodes.keys())
    # ESGAgent fan-out node naming follows existing pattern (lowercase)
    assert any("esg" in n.lower() for n in node_names)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/test_graph_wiring_new_agents.py -v`
Expected: FAIL — `risk_score not in node_names`

- [ ] **Step 4: Add imports and wire the new nodes in `graph.py`**

At the top of `src/orchestra_tprm/graph.py`, add:

```python
from orchestra_tprm.agents.risk_score import RiskScoreAgent
from orchestra_tprm.agents.remediation import RemediationAgent, should_run_remediation
```

Inside `build_graph(...)`, locate the section where `policy = PolicyAgent(...)` is constructed. Add immediately after:

```python
    # Load policy YAML for RiskScoreAgent (mirrors PolicyAgent's load)
    import yaml as _yaml
    from pathlib import Path as _Path
    _policy_data = _yaml.safe_load(
        _Path(cfg.policy_pack).read_text(encoding="utf-8")
    ) if not str(cfg.policy_pack).startswith("/") else _yaml.safe_load(
        # cfg.policy_pack may be a basename → resolve under policies/
        _Path(__file__).resolve().parent.joinpath("policies", cfg.policy_pack).read_text(encoding="utf-8")
    )
    risk_score = RiskScoreAgent(policy=_policy_data, model=cfg.policy_model)
    remediation = RemediationAgent(mode=cfg.name, model=cfg.policy_model)
```

Then find where `g.add_node("policy", AgentNode(agent=policy, ...))` is invoked. Immediately BEFORE it, add the `risk_score` node:

```python
    g.add_node(
        "risk_score",
        AgentNode(
            agent=risk_score,
            map_output=True,
            input_mapper=lambda s: s,
        ),
    )
```

Locate the edge that currently goes from the join (or last specialist) to `policy`. Re-route it: that edge now goes to `risk_score`, and a new edge goes from `risk_score → policy`.

Find where `g.add_node("coordinator", ...)` is wired. Add a `remediation` node BEFORE it (and AFTER `pmi_planner` if M&A):

```python
    g.add_node(
        "remediation",
        AgentNode(
            agent=remediation,
            map_output=True,
            input_mapper=lambda s: s,
        ),
    )
```

The edge that currently goes from `policy` (or `pmi_planner` in M&A) to `coordinator` now goes via `remediation`:

- Vendor mode: `policy → remediation → coordinator`
- M&A mode: `policy → pmi_planner → remediation → coordinator`

Because `RemediationAgent` internally honours `should_run_remediation(state)` and emits an empty plan when skipped, no conditional edge is required at the graph level. The agent always returns `{"remediation_plan": ...}`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/test_graph_wiring_new_agents.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Run a smoke test of the full graph build for both modes**

Run: `cd Orchestra && python -c "from orchestra_tprm.graph import build_graph; from orchestra_tprm.modes.config import ModeConfig; import yaml; from pathlib import Path; from types import SimpleNamespace; ad = SimpleNamespace(bq=None,sheets=None,docs=None,drive=None,github=None); cfg_v = ModeConfig(**yaml.safe_load(Path('src/orchestra_tprm/modes/vendor.yaml').read_text())); cfg_m = ModeConfig(**yaml.safe_load(Path('src/orchestra_tprm/modes/ma.yaml').read_text())); build_graph(cfg_v, adapters=ad); build_graph(cfg_m, adapters=ad); print('both graphs built')"`

Expected output: `both graphs built`

- [ ] **Step 7: Commit**

```bash
cd Orchestra
git add src/orchestra_tprm/graph.py \
        tests/tprm/unit/test_graph_wiring_new_agents.py
git commit -m "feat(graph): wire risk_score + remediation nodes into build_graph"
```

---

### Task 7: Coordinator template sections

**Files:**
- Modify: `src/orchestra_tprm/templates/coordinator_vendor.tmpl`
- Modify: `src/orchestra_tprm/templates/coordinator_ma.tmpl`
- Test: `tests/tprm/unit/test_coordinator_new_sections.py` (new)

- [ ] **Step 1: Locate template files and inspect format**

Run: `cd Orchestra && find src/orchestra_tprm/templates -type f -name '*.tmpl' -o -name '*.j2' 2>/dev/null`

If templates are not in `templates/`, run: `find src/orchestra_tprm -name 'coordinator_*' -type f`

Read both vendor and M&A templates to identify the existing section structure (Findings table, ICMemo, PMIPlan, etc.).

- [ ] **Step 2: Write the failing test**

```python
# tests/tprm/unit/test_coordinator_new_sections.py
"""Verify Coordinator renders Risk Score + Remediation Roadmap sections."""
from __future__ import annotations

import pytest

from orchestra_tprm.agents.coordinator import Coordinator
from orchestra_tprm.modes.config import ModeConfig
from orchestra_tprm.schemas import (
    Finding,
    RemediationItem,
    RemediationPlan,
    RiskDriver,
    RiskScore,
)


class _SheetsStub:
    def __init__(self):
        self.written: list[tuple[str, str]] = []
    async def write_section(self, sheet_id, title, body):
        self.written.append((title, body))
    async def append_section(self, sheet_id, title, body):
        self.written.append((title, body))


@pytest.fixture
def vendor_cfg() -> ModeConfig:
    import yaml
    from pathlib import Path
    data = yaml.safe_load(
        Path("src/orchestra_tprm/modes/vendor.yaml").read_text(encoding="utf-8")
    )
    return ModeConfig(**data)


async def test_coordinator_renders_risk_score_section(vendor_cfg) -> None:
    sheets = _SheetsStub()
    coord = Coordinator(mode_config=vendor_cfg, sheets=sheets, docs=None,
                        sheet_id="sheet-1", doc_id="")
    state = {
        "findings": [],
        "policy_verdict": "approve",
        "ic_memo": {},
        "risk_score": RiskScore(
            overall=42, verdict="amber",
            dimensions={"security": 60, "legal": 20},
            top_risk_drivers=[
                RiskDriver(dimension="security", finding_id="x", severity="high", one_liner="SOC2 gap"),
            ],
            explanation="Risk concentrated in security.",
        ),
        "remediation_plan": RemediationPlan(items=[], horizon_days=0, summary="No remediation required."),
    }
    await coord(state)  # or whatever the call surface is
    section_titles = [t for (t, _) in sheets.written]
    assert any("risk" in t.lower() and "score" in t.lower() for t in section_titles)


async def test_coordinator_renders_remediation_roadmap_section(vendor_cfg) -> None:
    sheets = _SheetsStub()
    coord = Coordinator(mode_config=vendor_cfg, sheets=sheets, docs=None,
                        sheet_id="sheet-1", doc_id="")
    items = [
        RemediationItem(
            finding_id="f1", action="Demand SOC2", owner="vendor",
            priority="P0", leverage="MSA 14.2", est_effort_days=30,
        ),
    ]
    state = {
        "findings": [],
        "policy_verdict": "conditional-approve",
        "ic_memo": {},
        "risk_score": None,
        "remediation_plan": RemediationPlan(items=items, horizon_days=30, summary="Close SOC2 gap."),
    }
    await coord(state)
    section_titles = [t for (t, _) in sheets.written]
    assert any("remediation" in t.lower() for t in section_titles)
```

Note: the exact `Coordinator.__call__` signature and the sheets/docs adapter call surface may differ. Adapt the test to match the actual Coordinator API discovered in Step 1.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/test_coordinator_new_sections.py -v`
Expected: FAIL — sections not yet rendered.

- [ ] **Step 4: Add Risk Score and Remediation Roadmap sections to `coordinator_vendor.tmpl`**

Append (or insert in the appropriate section ordering — typically after the header, before Findings table):

```
{% if risk_score %}
## Risk Score

{{ risk_score.overall }}/100 — **{{ risk_score.verdict|upper }}**

{{ risk_score.explanation }}

### Top Risk Drivers

{% for d in risk_score.top_risk_drivers %}
- **[{{ d.dimension }}]** ({{ d.severity }}) — {{ d.one_liner }}
{% endfor %}

### Per-Dimension Scores

{% for dim, score in risk_score.dimensions.items() %}
- {{ dim }}: {{ score }}/100
{% endfor %}

---
{% endif %}
```

After the Findings section, before any closing content, insert:

```
{% if remediation_plan and remediation_plan.items %}
## Remediation Roadmap

{{ remediation_plan.summary }}

Horizon: {{ remediation_plan.horizon_days }} days

{% for priority in ["P0", "P1", "P2"] %}
### {{ priority }}
{% for item in remediation_plan.items if item.priority == priority %}
- **{{ item.action }}** ({{ item.owner }}, ~{{ item.est_effort_days or "?" }}d)
  *Leverage:* {{ item.leverage }}
{% else %}
- _(none)_
{% endfor %}
{% endfor %}

---
{% elif remediation_plan %}
## Remediation Roadmap

{{ remediation_plan.summary }}

---
{% endif %}
```

- [ ] **Step 5: Apply the same template fragments to `coordinator_ma.tmpl`**

Identical fragments, but the Risk Score section goes BEFORE the ICMemo section (since the score informs the IC narrative), and the Remediation Roadmap section goes AFTER PMIPlan (since Remediation refines the PMI horizon).

- [ ] **Step 6: Inspect Coordinator code for state field plumbing**

Run: `cd Orchestra && grep -n 'risk_score\|remediation_plan\|render_context\|template_vars' src/orchestra_tprm/agents/coordinator.py | head -20`

If the Coordinator builds an explicit `render_context` dict for the template, add:

```python
render_context["risk_score"] = state.get("risk_score")
render_context["remediation_plan"] = state.get("remediation_plan")
```

If the Coordinator passes `state` directly to the template engine, no Python change is needed — the template's `{% if risk_score %}` will work out of the box.

- [ ] **Step 7: Run test to verify it passes**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/test_coordinator_new_sections.py -v`
Expected: PASS (2 tests). If the test failed because the Coordinator surface differs from the stub, adapt the test and re-run.

- [ ] **Step 8: Run all existing coordinator tests to confirm no regression**

Run: `cd Orchestra && python -m pytest tests/tprm/unit/ -k 'coordinator' -v`
Expected: All pre-existing coordinator tests still pass.

- [ ] **Step 9: Commit**

```bash
cd Orchestra
git add src/orchestra_tprm/templates/coordinator_vendor.tmpl \
        src/orchestra_tprm/templates/coordinator_ma.tmpl \
        src/orchestra_tprm/agents/coordinator.py \
        tests/tprm/unit/test_coordinator_new_sections.py
git commit -m "feat(coordinator): render Risk Score + Remediation Roadmap sections"
```

---

### Task 8: Dashboard — RiskScoreHero + RemediationRoadmap components

**Files:**
- Create: `dashboard/src/components/RiskScoreHero.tsx`
- Create: `dashboard/src/components/RemediationRoadmap.tsx`
- Modify: `dashboard/src/App.tsx`

- [ ] **Step 1: Inspect existing App.tsx for component layout**

Run: `cd Orchestra && grep -n 'import\|function App\|function Run\|<NodeCard\|findings\|verdict\|risk_score\|remediation' dashboard/src/App.tsx | head -40`

Identify (a) where the run-detail view is rendered, (b) the existing `useSSE` or fetch pattern for run state, (c) the import style and CSS class conventions.

- [ ] **Step 2: Create RiskScoreHero component**

Create `dashboard/src/components/RiskScoreHero.tsx`:

```tsx
import React from "react";

export interface RiskDriver {
  dimension: string;
  finding_id: string;
  severity: "low" | "medium" | "high" | "critical";
  one_liner: string;
}

export interface RiskScore {
  overall: number;
  verdict: "green" | "amber" | "red";
  dimensions: Record<string, number>;
  top_risk_drivers: RiskDriver[];
  explanation: string;
}

const VERDICT_STYLES: Record<RiskScore["verdict"], { bg: string; fg: string; label: string }> = {
  green: { bg: "#1c2a1f", fg: "#86efac", label: "GREEN" },
  amber: { bg: "#2a2317", fg: "#fbbf24", label: "AMBER" },
  red:   { bg: "#2a1717", fg: "#f87171", label: "RED" },
};

export const RiskScoreHero: React.FC<{ score: RiskScore | null }> = ({ score }) => {
  if (!score) return null;
  const v = VERDICT_STYLES[score.verdict];
  const sortedDims = Object.entries(score.dimensions).sort(([, a], [, b]) => b - a);

  return (
    <section
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(180px, auto) 1fr",
        gap: "24px",
        padding: "24px",
        background: "#0f1115",
        border: "1px solid #1f2329",
        borderRadius: "8px",
        marginBottom: "16px",
        fontFamily: "'Roboto Mono', monospace",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontSize: "72px", lineHeight: 1, fontWeight: 700, color: "#e6e9ef" }}>
          {score.overall}
        </div>
        <div style={{ fontSize: "11px", color: "#7a8390", marginTop: "4px" }}>RISK SCORE</div>
        <div
          style={{
            marginTop: "12px",
            padding: "4px 12px",
            borderRadius: "999px",
            background: v.bg,
            color: v.fg,
            fontSize: "12px",
            fontWeight: 600,
            letterSpacing: "0.05em",
          }}
        >
          {v.label}
        </div>
      </div>
      <div>
        <p style={{ color: "#c4cad4", marginTop: 0, fontStyle: "italic" }}>{score.explanation}</p>

        {score.top_risk_drivers.length > 0 && (
          <>
            <div style={{ color: "#7a8390", fontSize: "11px", margin: "12px 0 6px", letterSpacing: "0.05em" }}>
              TOP RISK DRIVERS
            </div>
            <ul style={{ listStyle: "none", padding: 0, margin: 0, color: "#e6e9ef" }}>
              {score.top_risk_drivers.map((d) => (
                <li key={d.finding_id} style={{ marginBottom: "6px", fontSize: "13px" }}>
                  <span style={{ color: "#7a8390" }}>[{d.dimension}]</span>{" "}
                  <span style={{ color: VERDICT_STYLES[d.severity === "critical" || d.severity === "high" ? "red" : d.severity === "medium" ? "amber" : "green"].fg }}>
                    ({d.severity})
                  </span>{" "}
                  {d.one_liner}
                </li>
              ))}
            </ul>
          </>
        )}

        <div style={{ color: "#7a8390", fontSize: "11px", margin: "16px 0 6px", letterSpacing: "0.05em" }}>
          PER-DIMENSION
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          {sortedDims.map(([dim, val]) => (
            <div key={dim} style={{ display: "grid", gridTemplateColumns: "120px 1fr 40px", alignItems: "center", gap: "8px", fontSize: "12px", color: "#c4cad4" }}>
              <span>{dim}</span>
              <div style={{ height: "8px", background: "#1f2329", borderRadius: "2px", overflow: "hidden" }}>
                <div
                  style={{
                    width: `${val}%`,
                    height: "100%",
                    background: val >= 70 ? VERDICT_STYLES.red.fg : val >= 31 ? VERDICT_STYLES.amber.fg : VERDICT_STYLES.green.fg,
                    transition: "width 300ms ease",
                  }}
                />
              </div>
              <span style={{ textAlign: "right", color: "#7a8390" }}>{val}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
```

- [ ] **Step 3: Create RemediationRoadmap component**

Create `dashboard/src/components/RemediationRoadmap.tsx`:

```tsx
import React, { useState } from "react";

export interface RemediationItem {
  finding_id: string;
  action: string;
  owner: "vendor" | "buyer" | "both";
  priority: "P0" | "P1" | "P2";
  leverage: string;
  est_effort_days: number | null;
}

export interface RemediationPlan {
  items: RemediationItem[];
  horizon_days: number;
  summary: string;
}

const PRIORITY_BG: Record<RemediationItem["priority"], string> = {
  P0: "#2a1717",
  P1: "#2a2317",
  P2: "#171f2a",
};

const PRIORITY_FG: Record<RemediationItem["priority"], string> = {
  P0: "#f87171",
  P1: "#fbbf24",
  P2: "#93c5fd",
};

export const RemediationRoadmap: React.FC<{ plan: RemediationPlan | null }> = ({ plan }) => {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (!plan) return null;

  const groupedItems = (["P0", "P1", "P2"] as const).map((p) => ({
    priority: p,
    items: plan.items.filter((i) => i.priority === p),
  }));

  const isEmpty = plan.items.length === 0;

  return (
    <section
      style={{
        padding: "24px",
        background: "#0f1115",
        border: "1px solid #1f2329",
        borderRadius: "8px",
        marginBottom: "16px",
        fontFamily: "'Roboto Mono', monospace",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "12px" }}>
        <h2 style={{ margin: 0, color: "#e6e9ef", fontSize: "18px", fontWeight: 600 }}>
          Remediation Roadmap
        </h2>
        {!isEmpty && (
          <span style={{ color: "#7a8390", fontSize: "12px" }}>
            Horizon: {plan.horizon_days}d
          </span>
        )}
      </div>
      <p style={{ color: "#c4cad4", marginTop: 0, fontStyle: "italic" }}>{plan.summary}</p>

      {!isEmpty && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "12px", marginTop: "16px" }}>
          {groupedItems.map((group) => (
            <div key={group.priority}>
              <div
                style={{
                  background: PRIORITY_BG[group.priority],
                  color: PRIORITY_FG[group.priority],
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  fontWeight: 600,
                  letterSpacing: "0.05em",
                  marginBottom: "8px",
                  display: "inline-block",
                }}
              >
                {group.priority}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {group.items.length === 0 ? (
                  <div style={{ color: "#7a8390", fontSize: "12px", fontStyle: "italic" }}>—</div>
                ) : (
                  group.items.map((item) => (
                    <div
                      key={item.finding_id}
                      onClick={() => setExpanded(expanded === item.finding_id ? null : item.finding_id)}
                      style={{
                        padding: "12px",
                        background: "#15181e",
                        border: "1px solid #1f2329",
                        borderRadius: "4px",
                        cursor: "pointer",
                        fontSize: "13px",
                        color: "#e6e9ef",
                      }}
                    >
                      <div style={{ fontWeight: 500 }}>{item.action}</div>
                      <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
                        <span
                          style={{
                            padding: "2px 6px",
                            background: "#1f2329",
                            borderRadius: "2px",
                            fontSize: "10px",
                            color: "#c4cad4",
                          }}
                        >
                          {item.owner}
                        </span>
                        {item.est_effort_days != null && (
                          <span style={{ fontSize: "10px", color: "#7a8390" }}>
                            ~{item.est_effort_days}d
                          </span>
                        )}
                      </div>
                      {expanded === item.finding_id && (
                        <div style={{ marginTop: "8px", fontSize: "11px", color: "#c4cad4" }}>
                          <span style={{ color: "#7a8390" }}>Leverage:</span> {item.leverage}
                          <br />
                          <span style={{ color: "#7a8390" }}>Finding ID:</span> {item.finding_id.slice(0, 8)}…
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};
```

- [ ] **Step 4: Mount the new components in App.tsx**

Add the two imports at the top:

```tsx
import { RiskScoreHero, RiskScore } from "./components/RiskScoreHero";
import { RemediationRoadmap, RemediationPlan } from "./components/RemediationRoadmap";
```

In the run-detail view (look for where findings are rendered or where the SSE run state is unpacked), add the two components ABOVE the findings table:

```tsx
<RiskScoreHero score={(runState.risk_score as RiskScore) ?? null} />
<RemediationRoadmap plan={(runState.remediation_plan as RemediationPlan) ?? null} />
```

If `runState` is typed, extend its type to include `risk_score?: RiskScore | null` and `remediation_plan?: RemediationPlan | null`.

- [ ] **Step 5: Type-check and build**

Run: `cd Orchestra/dashboard && npm run build 2>&1 | tail -30`
Expected: clean build, no TS errors.

If there are TS errors, fix them inline. Common issues: missing React types, props mismatch on existing components.

- [ ] **Step 6: Smoke-test the dashboard locally**

Run (background): `cd Orchestra && ./dev.ps1` or `cd Orchestra/dashboard && npm run dev`

Open `http://localhost:5173` (or whichever port Vite picks). Trigger a fake run via the existing landing-page flow. Verify that:
- RiskScoreHero renders when `risk_score` is in state (no console errors when null).
- RemediationRoadmap renders with the 3-column layout when `remediation_plan.items` is non-empty.
- Cards are clickable to expand the leverage detail.

If no easy way to populate state for the smoke test, defer visual verification to the post-redeploy live run.

- [ ] **Step 7: Commit**

```bash
cd Orchestra
git add dashboard/src/components/RiskScoreHero.tsx \
        dashboard/src/components/RemediationRoadmap.tsx \
        dashboard/src/App.tsx
git commit -m "feat(dashboard): RiskScoreHero + RemediationRoadmap components"
```

---

### Task 9: Cloud Run redeploy + live smoke test

**Files:**
- (No file changes; deploy + verify)

- [ ] **Step 1: Confirm Docker build succeeds locally**

Run: `cd Orchestra && docker build -t orchestra-tprm:test . 2>&1 | tail -15`
Expected: successful build, image tagged.

If the build fails on the React stage, run `cd Orchestra/dashboard && npm install && npm run build` first to surface npm errors directly.

- [ ] **Step 2: Trigger the Cloud Run workflow OR run the deploy script**

Option A (CI): `cd Orchestra && git push origin main` then `gh workflow run cloud-run.yml` (if the workflow is dispatchable).

Option B (manual via Terraform): `cd Orchestra/terraform && make deploy` (if a Make target exists).

Inspect output for the final Cloud Run service URL. Save it as `$DEMO_URL`.

- [ ] **Step 3: Health-check the deployed URL**

Run: `curl -sf "$DEMO_URL/healthz" || curl -sf "$DEMO_URL/api/v1/health"`
Expected: 200 with a JSON `{"status":"ok"}` (exact path depends on the FastAPI route — check `src/orchestra_tprm/server.py` or wherever the routes are registered).

- [ ] **Step 4: Run a HashiCorp end-to-end smoke via the deployed dashboard**

Open `$DEMO_URL` in a browser. Use the HashiCorp example tile (or the equivalent landing-page entry point). Confirm:
- SSE stream connects (no "Connection lost" errors per memory's known fix).
- All specialists fan out and complete (NodeCards light up).
- After join: `risk_score` event fires, RiskScoreHero renders.
- After policy: `remediation_plan` event fires, RemediationRoadmap renders.
- Coordinator writes the Sheet (or Doc in M&A mode). URL is reachable.

If the run fails with a Gemini 429, capture the network log and proceed to Task 10 (replay fallback).

- [ ] **Step 5: Capture screenshots for the slide deck**

Take 4 screenshots:
1. Landing page with HashiCorp + Acme tiles
2. Dashboard mid-run (NodeCards lighting up)
3. RiskScoreHero in full render
4. RemediationRoadmap in full render

Save to `Orchestra/docs/submission/screenshots/`.

- [ ] **Step 6: Commit screenshots and the recorded URL**

```bash
cd Orchestra
mkdir -p docs/submission
echo "DEMO_URL=$DEMO_URL" > docs/submission/cloud-run-url.txt
git add docs/submission/screenshots/ docs/submission/cloud-run-url.txt
git commit -m "docs(submission): Cloud Run demo URL + dashboard screenshots"
```

---

### Task 10: Re-capture replay JSONLs for HashiCorp + Acme

**Files:**
- Create/overwrite: `examples/tprm/hashicorp/replay.jsonl`
- Overwrite: `examples/tprm/acme/replay.jsonl`

- [ ] **Step 1: Confirm `--record-replay` flag is wired in the CLI**

Run: `cd Orchestra && python -m orchestra_tprm --help 2>&1 | grep -i replay`
Expected: `--record-replay <path>` and `--replay <path>` are both listed.

- [ ] **Step 2: Capture HashiCorp replay against live Gemini**

Run:

```bash
cd Orchestra
export GOOGLE_API_KEY="<your-key>"
python -m orchestra_tprm \
  --mode vendor \
  --packet examples/tprm/hashicorp \
  --record-replay examples/tprm/hashicorp/replay.jsonl \
  --subject HashiCorp \
  2>&1 | tail -30
```

Expected: run completes with a non-empty `replay.jsonl`. Inspect file size: `ls -la examples/tprm/hashicorp/replay.jsonl` — should be ≥ a few KB.

- [ ] **Step 3: Capture Acme replay**

Run:

```bash
cd Orchestra
python -m orchestra_tprm \
  --mode ma \
  --packet examples/tprm/acme \
  --record-replay examples/tprm/acme/replay.jsonl \
  --subject "Acme Corp" \
  2>&1 | tail -30
```

Expected: run completes; `replay.jsonl` overwritten with new content that includes calls for the 3 new agents.

- [ ] **Step 4: Verify both replays roundtrip**

Run:

```bash
cd Orchestra
python -m orchestra_tprm --mode vendor --packet examples/tprm/hashicorp --replay examples/tprm/hashicorp/replay.jsonl --subject HashiCorp 2>&1 | tail -10
python -m orchestra_tprm --mode ma --packet examples/tprm/acme --replay examples/tprm/acme/replay.jsonl --subject "Acme Corp" 2>&1 | tail -10
```

Expected: both runs complete without errors and produce findings + risk_score + remediation_plan in their output verdict JSON.

- [ ] **Step 5: Fallback path — if Gemini 429 prevents live capture**

If quota is exhausted, hand-write a minimal replay JSONL using test-fixture LLM responses as templates. The replay file is line-delimited JSON where each line is a serialized `LLMCalled` event with input messages and output content. Use `src/orchestra/storage/events.py:LLMCalled` as the schema reference.

Use this Python one-liner template to generate one JSONL line per scripted LLM response (replace the inputs and outputs with the actual test fixtures):

```bash
cd Orchestra
python -c "
import json
events = [
    {'kind': 'LLMCalled', 'agent': 'LegalAgent', 'request': {...}, 'response': {'content': '[...]'}},
    # ... one per LLM call in the pipeline
]
with open('examples/tprm/hashicorp/replay.jsonl', 'w') as f:
    for e in events: f.write(json.dumps(e) + '\n')
"
```

This is a fallback only; live capture is strongly preferred.

- [ ] **Step 6: Commit the captured replays**

```bash
cd Orchestra
git add examples/tprm/hashicorp/replay.jsonl examples/tprm/acme/replay.jsonl
git commit -m "feat(replay): capture HashiCorp + Acme replays with 3 new agents"
```

- [ ] **Step 7: Final regression run of the full test suite**

Run: `cd Orchestra && python -m pytest tests/tprm/ -x --timeout=60 2>&1 | tail -30`
Expected: green or only-skipped. If red, fix the breakage before declaring done.

---

## Hand-off to submission tasks

After all 10 tasks complete and the final regression run is green, the agent-build phase is done. The downstream submission tasks (cover image, slide deck, video, lablab.ai form) are tracked in the parent TaskList (#7-#11) and do not require code changes in this plan.

The Cloud Run demo URL recorded in `docs/submission/cloud-run-url.txt` is the canonical URL for slides 6-9 and the submission form. The screenshots captured in Task 9 Step 5 are the source material for slides 7-8.

---

## Self-Review

**Spec coverage:**
- §3 (file list) → mapped to Tasks 1-8 file-by-file ✓
- §4 (schemas) → Task 1 ✓
- §5 (Risk Score formula) → Task 4 step 4 + test step 1 case 3 ✓
- §6 (Remediation skip predicate) → Task 5 step 3 (function definition) + test cases 1-4 ✓
- §7 (mode-aware prompts) → Task 5 step 3 (two system prompts) ✓
- §8 (ESG specialist + router + policy YAMLs) → Tasks 2 + 3 ✓
- §9 (graph wiring) → Task 6 ✓
- §10 (Coordinator templates) → Task 7 ✓
- §11 (Dashboard components) → Task 8 ✓
- §12 (Replay strategy) → Task 10 ✓
- §13 (test patterns) → embedded in each task's TDD ✓
- §14 (execution sequence) → matches task order ✓
- §15 (risks) → addressed inline (fail-soft in Task 4, fallback in Task 10) ✓

**Placeholder scan:** No "TBD" / "TODO" / "add validation" / "handle edge cases" found. All code blocks are concrete. ✓

**Type consistency:**
- `Finding.id` referenced consistently as `str` (UUID4 hex or with dashes — Task 1 step 3 reconciles)
- `RiskScore.verdict` is `Literal["green", "amber", "red"]` in schemas (Task 1) and matched in TypeScript (Task 8)
- `RemediationItem.priority` is `Literal["P0","P1","P2"]` in Python and TypeScript ✓
- `RemediationItem.owner` is `Literal["vendor","buyer","both"]` in both ✓
- `should_run_remediation` signature: `(state: dict) -> bool` consistent between Task 5 (definition) and Task 6 (graph usage note) ✓

No issues found. Plan ready for execution.
