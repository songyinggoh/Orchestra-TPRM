# Delta-Design — Risk Scoring + Remediation + ESG (Option B)

**Parent spec:** [`2026-05-16-hackathon-submission-design.md`](2026-05-16-hackathon-submission-design.md)
**Date:** 2026-05-18
**Status:** Locked, ready for plan
**Owner:** this instance
**Deadline gate:** 2026-05-19 06:00 SGT (2hr buffer before 08:00 hard)

## 1. Context

The parent spec (§5.1-5.3 and decisions D-13 through D-17) commits to three new agents — Risk Scoring, Remediation, ESG — as the originality differentiators. The implementation pivoted toward M&A due-diligence (SaaSMetrics + PMIPlanner + ICMemo) and the three originality agents were never written. Success Criterion #6 still asserts they exist. Slide §7.3 #10-#12 spotlights them. We close the gap here.

This delta refines the parent spec where it left implementation-level details open. Where the parent is concrete (file paths, output schema fields, graph positions, verdict thresholds), we don't restate — we cite.

## 2. Scope (delta only)

In:
- 3 new agent files + 3 test files + 2 dashboard components
- Schema additions (`RiskScore`, `RiskDriver`, `RemediationItem`, `RemediationPlan`)
- TPRMState additions (`risk_score`, `remediation_plan`)
- Graph re-wiring in `build_graph`
- Coordinator template patches (`coordinator_vendor.tmpl`, `coordinator_ma.tmpl`)
- Mode YAML additions (`esg: gemini-2.5-flash` in both modes)
- Policy pack additions (`risk_score_thresholds`, ESG `critical_categories`)
- DocRouter prompt extension for ESG document kinds
- Replay JSONL re-capture for HashiCorp + Acme

Out:
- BigQuery aggregation tables for `risk_score` / `remediation_plan` (post-deadline)
- M&A-specific Remediation tuning beyond prompt mode-switch
- Re-running 261-test suite to chase regressions — run once after each agent lands, fix only if red

## 3. Files

| Path | Purpose |
|---|---|
| `src/orchestra_tprm/agents/risk_score.py` | RiskScoreAgent — deterministic math + LLM rationale |
| `src/orchestra_tprm/agents/remediation.py` | RemediationAgent — mode-aware action plan, skip-aware |
| `src/orchestra_tprm/agents/specialists/esg.py` | ESGAgent — 7th specialist, mirrors `legal.py` shape |
| `src/orchestra_tprm/schemas.py` | (edit) add 4 models + 2 TPRMState fields |
| `src/orchestra_tprm/graph.py` | (edit) wire risk_score + remediation nodes |
| `src/orchestra_tprm/agents/router.py` | (edit) extend kind taxonomy with esg-* tags |
| `src/orchestra_tprm/modes/vendor.yaml` | (edit) add `esg: gemini-2.5-flash` |
| `src/orchestra_tprm/modes/ma.yaml` | (edit) add `esg: gemini-2.5-flash` |
| `src/orchestra_tprm/policies/vendor.yaml` | (edit) add `risk_score_thresholds` + ESG critical_categories |
| `src/orchestra_tprm/policies/ma.yaml` | (edit) add `risk_score_thresholds` + ESG critical_categories |
| `src/orchestra_tprm/templates/coordinator_vendor.tmpl` | (edit) render risk_score + remediation sections |
| `src/orchestra_tprm/templates/coordinator_ma.tmpl` | (edit) render risk_score + remediation sections |
| `tests/unit/test_risk_score_agent.py` | unit test, scripted-LLM |
| `tests/unit/test_remediation_agent.py` | unit test, scripted-LLM, includes skip path |
| `tests/unit/test_esg_agent.py` | unit test, scripted-LLM |
| `tests/unit/test_graph_wiring.py` | (edit) assert new node order |
| `dashboard/src/components/RiskScoreHero.tsx` | UI — 0-100 gauge + verdict pill + dimension bars |
| `dashboard/src/components/RemediationRoadmap.tsx` | UI — P0/P1/P2 Kanban with finding_id join |
| `dashboard/src/App.tsx` | (edit) mount new components in run-detail view |
| `examples/tprm/hashicorp/replay.jsonl` | new — captured after agents land |
| `examples/tprm/acme/replay.jsonl` | regenerated — captured after agents land |

## 4. Schemas

`Finding.id` already exists as `Field(default_factory=lambda: str(uuid.uuid4()))` (line ~75 of `schemas.py`). D-17 from parent spec is satisfied.

Add to `schemas.py`:

```python
class RiskDriver(BaseModel):
    dimension: str                                  # e.g. "security"
    finding_id: str
    severity: SeverityLiteral
    one_liner: str                                  # LLM-generated, 1 sentence


class RiskScore(BaseModel):
    overall: int                                    # 0..100, higher = riskier
    verdict: Literal["green", "amber", "red"]
    dimensions: dict[str, int]                      # {agent_name: 0..100}
    top_risk_drivers: list[RiskDriver]              # at most 3
    explanation: str                                # LLM-generated, 1-2 sentences


class RemediationItem(BaseModel):
    finding_id: str
    action: str                                     # imperative
    owner: Literal["vendor", "buyer", "both"]
    priority: Literal["P0", "P1", "P2"]
    leverage: str                                   # contract clause / cert / escrow term
    est_effort_days: int | None = None


class RemediationPlan(BaseModel):
    items: list[RemediationItem]
    horizon_days: int                               # max est_effort_days, default 90
    summary: str                                    # 1 sentence
```

Add to `TPRMState` (TypedDict):

```python
risk_score: RiskScore | None
remediation_plan: RemediationPlan | None
```

## 5. Risk Scoring formula

```python
weights = policy["weights"]                          # e.g. {"low":1,"medium":3,"high":7,"critical":15}
weighted_sum = sum(weights[f.severity] for f in findings)
max_possible = max(len(findings), 1) * weights["critical"]
overall = round(100 * weighted_sum / max_possible)
overall = min(100, max(0, overall))
```

Per-dimension (`dimensions[agent_name]`): same formula scoped to `[f for f in findings if f.agent == agent_name]`. Dimensions present only for agents that emitted ≥1 finding.

Verdict thresholds in `policies/{vendor,ma}.yaml` under `risk_score_thresholds`:
- Vendor: `{green_max: 30, amber_max: 69}` → red ≥70
- M&A: `{green_max: 20, amber_max: 59}` → red ≥60

Top 3 drivers: `sorted(findings, key=lambda f: -weights[f.severity])[:3]`.

LLM call: one Gemini-2.5-Flash call producing structured output:
```json
{
  "explanation": "<1-2 sentences>",
  "driver_one_liners": ["<sentence for #1>", "<sentence for #2>", "<sentence for #3>"]
}
```

**Fallback if LLM fails:** `explanation = "Risk concentrated in {top_dim_1}, {top_dim_2}."`, `one_liner = f.summary[:120]` per driver. Demo never crashes on Gemini 429.

## 6. Remediation skip predicate

```python
def should_run_remediation(state: dict) -> bool:
    verdict = state.get("policy_verdict") or (state.get("ic_memo") or {}).get("recommendation")
    findings = state.get("findings", [])
    has_medium_plus = any(
        Finding(**f if isinstance(f, dict) else f.model_dump()).severity in ("medium","high","critical")
        for f in findings
    )
    # In vendor mode, "approve" is the green-light verdict; in M&A, "proceed" is.
    approve_verdicts = {"approve", "proceed"}
    return not (verdict in approve_verdicts and not has_medium_plus)
```

When skipped, Remediation node emits an empty `RemediationPlan(items=[], horizon_days=0, summary="No remediation required — clean approval.")` so downstream consumers (Coordinator, Dashboard) always have something to render.

## 7. Remediation prompt (mode-aware)

Vendor framing (system prompt header):
> You are a vendor-onboarding remediation analyst. For each finding, write the action the **vendor** must take before contract signing. Owner is usually "vendor". Leverage refers to the contract clause, certification, or evidence we can demand.

M&A framing (system prompt header):
> You are an M&A deal-structuring analyst. For each finding, write the action the **buyer** can take to mitigate it via deal terms: price reduction, indemnity, escrow, rep-and-warranty insurance, or post-close monitoring. Owner is usually "buyer". Leverage refers to the specific SPA clause or escrow term.

Both share the structured-output schema (`RemediationPlan`).

## 8. ESG specialist

File: `src/orchestra_tprm/agents/specialists/esg.py`. Mirrors `legal.py` structure (loop over routed docs, LLM call per doc, return `list[Finding]`).

System prompt outline:
```
You are an ESG (Environmental, Social, Governance) compliance analyst.
Extract findings against this checklist:

Environmental:
  - Net-zero commitment year (target ≤ 2050)
  - Scope 1/2/3 emissions disclosure
  - Renewable energy mix
  - E-waste / circular economy policy
Social:
  - DEI metrics (board, workforce, pay equity)
  - Supply-chain labour audit cadence
  - Modern slavery statement (UK MSA 2015 / AU MSA 2018 compliant)
  - Customer privacy framework
Governance:
  - Board independence ratio
  - Audit committee composition
  - Anti-corruption / anti-bribery policy
  - Whistleblower protection
  - SOC 2 / ISO 27001 audit cadence

For each gap, emit:
  agent: "esg"
  category: "<kebab-case>"
  severity: "low"|"medium"|"high"|"critical"
  summary: "<one sentence>"
  evidence: [{ file_id, page, snippet }]
  workstream: "esg"
```

Vendor & M&A mode YAMLs both get `esg: gemini-2.5-flash`. Vendor mode active count: 5. M&A mode active count: 7.

`router.py` kind taxonomy adds:
- `sustainability-report`, `code-of-conduct`, `diversity-report`, `governance-disclosure`
All four route to `esg`.

`policies/vendor.yaml` and `policies/ma.yaml` add (under existing `critical_categories`):
```yaml
critical_categories:
  - ...existing...
  - net-zero-commitment
  - modern-slavery-statement
  - anti-corruption-policy
```

## 9. Graph wiring

Before (current):
```
bootstrap → intake → router → [specialists in parallel] → join → policy → [pmi_planner if M&A] → coordinator → END
```

After:
```
bootstrap → intake → router → [specialists in parallel] → join → risk_score → policy → [pmi_planner if M&A] → remediation_gate → remediation? → coordinator → END
```

- `risk_score` is a single `AgentNode` between the implicit join and `policy`. Always runs (both modes).
- `remediation_gate` is a tiny conditional-edge function returning either `"remediation"` or `"coordinator"` based on `should_run_remediation(state)`.
- When Remediation runs, edge goes `remediation → coordinator`. When skipped, the gate writes the empty `RemediationPlan` directly into state and edges to `coordinator`.

Implementation note: `WorkflowGraph` already supports `add_conditional_edges` (used elsewhere); reuse the pattern.

## 10. Coordinator rendering

Two new sections in both templates:

**Risk Score** (rendered first, before existing Findings section):
```
Risk Score: {risk_score.overall}/100 ({risk_score.verdict|upper})

{risk_score.explanation}

Top risk drivers:
  - [{driver.dimension}] {driver.one_liner}
  - ...

Per-dimension scores:
  {dim}: {score}/100
```

**Remediation Roadmap** (rendered after Findings, before existing ICMemo/PMIPlan sections):
```
Remediation Roadmap (P0 → P1 → P2)

P0 (immediate):
  - {item.action}  [owner: {item.owner}, leverage: {item.leverage}]
  - ...

P1 (within 30d):
  - ...

P2 (within {horizon_days}d):
  - ...
```

Both new sections gate on `state.risk_score is not None` / `state.remediation_plan and state.remediation_plan.items` to remain backward-compatible with replay JSONLs that don't have them.

## 11. Dashboard components

`dashboard/src/components/RiskScoreHero.tsx`:
- Big numeric (0-100) left
- Verdict pill (GREEN / AMBER / RED) using muted palette (no Google brand colours per memory: red `#b91c1c`, amber `#b45309`, green `#15803d` — slate-tinted)
- Horizontal bar chart of `dimensions` (CSS-only `<div>` widths, no chart lib)
- Below: 3 driver one-liners in a vertical list
- `explanation` rendered as italic caption

`dashboard/src/components/RemediationRoadmap.tsx`:
- 3-column Kanban (P0 / P1 / P2)
- Each card: `action` (title), `owner` chip, `leverage` (caption), expandable to show linked Finding via `finding_id`
- Empty state: "No remediation required — clean approval."

Both components imported into `App.tsx` and rendered after the existing run-detail header and findings table.

## 12. Replay strategy

Adding 3 new LLM-calling nodes invalidates any existing replay JSONL. Plan:

1. Develop all 3 agents with scripted-LLM responses in tests (zero Gemini cost).
2. Once green: trigger Cloud Run redeploy and run two `--record-replay` captures:
   - HashiCorp (no existing replay) → `examples/tprm/hashicorp/replay.jsonl`
   - Acme (existing replay stale) → overwrite `examples/tprm/acme/replay.jsonl`
3. Commit both to git (D-22).
4. Live judging path: judges hit HashiCorp tile → live Gemini. If 429, frontend auto-fallback uses replay JSONL (D-20). Same for Acme.

Capture cost: ~5 min per vendor at gemini-2.5-flash. If quota exhausts, hand-write scripted JSONL using the test-fixture LLM responses as a template.

## 13. Tests

Mirror `tests/unit/test_saas_metrics_agent.py` pattern: ScriptedLLM fixture, single agent under test, 3-5 cases each.

| Test file | Cases |
|---|---|
| `test_risk_score_agent.py` | (1) empty findings → 0/green (2) all critical → 100/red (3) mixed → math correct (4) LLM-fail → fallback string (5) per-dimension scoping |
| `test_remediation_agent.py` | (1) skip path (approve + zero ≥medium) (2) vendor framing (3) M&A framing (4) horizon_days = max est_effort_days (5) empty plan when no findings |
| `test_esg_agent.py` | (1) no routed docs → informational finding (2) Net-Zero gap → critical (3) modern-slavery statement → high (4) full disclosure → no findings |
| `test_graph_wiring.py` (extension) | (1) risk_score runs between specialists and policy (2) remediation skipped on clean approve (3) ESG present in both mode_configs |

## 14. Execution sequence (for the plan)

This is the order the writing-plans skill should serialize into the plan. Each step is gated on its predecessor being green.

1. Schemas patch (~20 min) — 5 new models, 2 TPRMState fields. Unblocks everything.
2. ESG specialist + router taxonomy + mode YAMLs (~60 min) — pure addition; existing tests stay green.
3. RiskScoreAgent + thresholds in policy YAMLs (~75 min) — deterministic math first, LLM rationale second.
4. RemediationAgent + skip gate (~75 min) — biggest LLM-prompt design.
5. Graph wiring + integration scripted-LLM test (~30 min).
6. Coordinator template patches (~30 min) — Jinja edits only.
7. Dashboard components (~90 min) — RiskScoreHero, RemediationRoadmap, App.tsx mount.
8. Cloud Run redeploy + smoke test (~30 min).
9. Replay capture HashiCorp + Acme (~15 min).
10. Cover image + slide deck + video + form fill (~6-7h) — outside this delta but downstream-gated by it.

Total for steps 1-9: ~7h. Buffer: ~1h.

## 15. Risk register (delta-specific)

| ID | Risk | Likelihood | Mitigation |
|---|---|---|---|
| R-D1 | Re-capture replay 429s on quota | Medium | Hand-write scripted JSONL from test fixtures |
| R-D2 | New schema fields break existing replay JSONLs | High (certain) | Coordinator templates guard `risk_score is not None`; replay JSONL re-captured anyway |
| R-D3 | Risk Score formula produces all 100s if every finding is critical | Low (by design) | Documented as expected behaviour in §5 |
| R-D4 | ESG documents not in example packets | Medium | Add 1-2 ESG-flavoured PDFs to `examples/tprm/{hashicorp,acme}/` or rely on absence → "no docs routed" informational finding |
| R-D5 | Dashboard cards push run-detail height past first-screen fold | Low | Collapse Remediation P2/P1 by default; expand on click |
| R-D6 | Coordinator template changes silently break old Sheets/Docs | Low | New sections are append-only; existing section order preserved |

## 16. Decisions log (delta)

| ID | Decision | Section |
|---|---|---|
| DD-01 | ESG is added as 7th specialist (not 6th — saas_metrics already exists). Both modes get it. | §8 |
| DD-02 | Risk Score LLM call is fail-soft: deterministic math always succeeds; rationale falls back to template string | §5 |
| DD-03 | Remediation skip predicate uses both vendor `policy_verdict == "approve"` and M&A `ic_memo.recommendation == "proceed"` | §6 |
| DD-04 | Remediation when skipped still emits empty `RemediationPlan` so downstream rendering is uniform | §6 |
| DD-05 | Coordinator templates gate new sections on `is not None` to remain replay-compatible | §10 |
| DD-06 | Dashboard uses CSS-only bar charts, no chart library (bundle size + Google MD3 palette adherence) | §11 |
| DD-07 | Re-capture both Acme + HashiCorp replays after agents land; commit JSONL | §12 |
| DD-08 | Existing 261-test suite is run once after each agent lands; only red tests get fixed (no churn-pass) | §2 |

**End of delta.** Ready for writing-plans.
