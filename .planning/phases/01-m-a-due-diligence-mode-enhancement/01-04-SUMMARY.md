---
phase: 01-m-a-due-diligence-mode-enhancement
plan: "04"
subsystem: saas-metrics-specialist
tags: [agents, saas-metrics, ma, new-specialist, financial]
dependency_graph:
  requires:
    - Finding with ic_decision/workstream/exposure_usd_range fields (Plan 01-01)
  provides:
    - SaaSMetricsAgent class at src/orchestra_tprm/agents/specialists/saas_metrics.py
    - SaaSMetricsAgent exported from orchestra_tprm.agents.specialists
  affects:
    - graph.py _build_specialists fan-out (Plan 06 will wire SaaSMetricsAgent node)
    - PolicyAgent IC classification (Plan 03) — will receive saas-metric findings with ic_decision tags
    - Coordinator IC memo (Plan 07) — saas deal-stoppers flow into risk register
tech_stack:
  added: []
  patterns:
    - BaseTPRMAgent subclass pattern (identical to financial.py, legal.py)
    - ic_decision clamping to known 4-value set (guards against LLM hallucinating new labels)
    - exposure_usd_range as (int,int) tuple from separate low/high LLM fields
    - no-docs fallback emits informational Finding rather than silent []
key_files:
  created:
    - src/orchestra_tprm/agents/specialists/saas_metrics.py
  modified:
    - src/orchestra_tprm/agents/specialists/__init__.py
decisions:
  - No-docs fallback emits one informational Finding (category=saas-metrics-no-docs) rather than [] — ensures audit trail when financial docs are missing from VDR
  - ic_decision clamping: any unknown LLM label → "post-close-monitoring" (safe fallback)
  - exposure_usd_range: both low AND high must be present and parseable as int, else None
  - Parse-error Findings carry workstream="financial" so they appear in financial workstream output
metrics:
  duration: "~3 minutes"
  completed: "2026-05-17T18:02:54Z"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 01 Plan 04: SaaSMetricsAgent Specialist Summary

New M&A-only parallel specialist SaaSMetricsAgent with 7 locked red-flag thresholds (NRR/GRR/logo-retention/Rule-of-40/CAC-payback/API-concentration) emitting workstream=financial Findings with ic_decision tags.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Create SaaSMetricsAgent specialist with red-flag threshold prompt | c09d5b8 | saas_metrics.py (new, 225 lines) |
| 2 | Export SaaSMetricsAgent from the specialists package | bb1e41a | specialists/__init__.py |

## What Was Built

### SaaSMetricsAgent (`src/orchestra_tprm/agents/specialists/saas_metrics.py`)

A new `BaseTPRMAgent` subclass, M&A mode only. Follows the `financial.py` structure exactly:

- `name = "SaaSMetricsAgent"` — matches the routing key used by DocRouterAgent
- `model = "gemini-2.5-pro"` (default) — financial docs warrant the stronger model
- Implements `_emit_findings(ctx: ExecutionContext) -> list[Finding]`

### `_SYSTEM` prompt structure

Two sections:

**Metric extraction list** — 9 SaaS metrics the LLM must look for:
`arr_usd`, `nrr_pct`, `grr_pct`, `logo_retention_pct`, `cac_payback_months`,
`ltv_cac_ratio`, `rule_of_40`, `api_concentration_pct`, `seat_vs_usage_mix`

**RED-FLAG THRESHOLDS table** — 7 locked thresholds verbatim per 01-CONTEXT.md:
| Threshold | ic_decision |
|-----------|-------------|
| NRR < 100% | price-adjustment |
| NRR < 90% | deal-stopper |
| Logo retention < 85% | deal-stopper |
| GRR < 80% (SMB context) | price-adjustment |
| CAC payback > 24 months | price-adjustment |
| Rule of 40 < 20 | price-adjustment |
| API contract concentration > 40% ARR | SPA-protection |
| Otherwise | post-close-monitoring |

The LLM applies these directly per metric and emits `ic_decision` in each JSON object.

### No-docs fallback Finding

When `routing.get("SaaSMetricsAgent", [])` is empty, returns immediately with one Finding:
```python
Finding(
    agent="SaaSMetricsAgent",
    category="saas-metrics-no-docs",
    severity="low",
    summary="No financial / investor documents were routed to SaaSMetricsAgent — SaaS metrics could not be assessed.",
    workstream="financial",
    ic_decision="post-close-monitoring",
)
```
This ensures a paper trail in the IC memo when financial documents were not provided to the VDR.

### ic_decision clamping logic

After receiving `ic_decision` from the LLM, the agent validates it against the known 4-value set:
```python
if ic_raw not in {"deal-stopper", "price-adjustment", "SPA-protection", "post-close-monitoring"}:
    ic_raw = "post-close-monitoring"
```
Defends against the LLM emitting labels not in the Literal type (e.g., "needs-review", "flag-for-discussion"), which would cause Pydantic validation errors on `Finding.ic_decision`.

### exposure_usd_range parsing

The LLM emits two separate fields (`exposure_usd_low`, `exposure_usd_high`) which are cast to an `(int, int)` tuple:
```python
if lo is not None and hi is not None:
    try:
        exposure_range = (int(lo), int(hi))
    except (TypeError, ValueError):
        exposure_range = None
else:
    exposure_range = None
```
Rule: **both** bounds must be present AND parseable as int. If either is missing or unparseable, `exposure_usd_range=None` on the Finding. Partial data is discarded rather than silently substituting 0.

### Package export (`src/orchestra_tprm/agents/specialists/__init__.py`)

Import added in alphabetical position (after `legal`, before `security`). `__all__` expanded to multi-line sorted list with `SaaSMetricsAgent` between `LegalAgent` and `SecurityAgent`.

## Deviations from Plan

None — plan executed exactly as written. The agent code in the plan's `<action>` block was used verbatim without any structural changes.

## Test Results

- No-docs fallback: verified (ScriptedLLM([]) → 1 Finding, correct fields)
- Happy-path: verified (ScriptedLLM returns NRR=88% → deal-stopper, workstream=financial, exposure=(0,5000000))
- 233 existing unit tests: all pass (no regressions)

## Known Stubs

None — agent reads real documents via `read_uri` / Gemini attachments. The LLM call is live; no mock data flows to output. Plan 06 will wire the graph node.

## Threat Flags

None — no new network endpoints, auth paths, or file access patterns introduced. The `read_uri` helper was already used by all other specialists.

## Self-Check: PASSED

- `src/orchestra_tprm/agents/specialists/saas_metrics.py` — exists, 225 lines
- `src/orchestra_tprm/agents/specialists/__init__.py` — contains `from .saas_metrics import SaaSMetricsAgent` and `"SaaSMetricsAgent"` in `__all__`
- Commit c09d5b8 — Task 1 (saas_metrics.py)
- Commit bb1e41a — Task 2 (__init__.py export)
- All 7 thresholds present in `_SYSTEM`
- 233 unit tests pass
