---
phase: 01-m-a-due-diligence-mode-enhancement
plan: "06"
subsystem: graph-wiring
tags: [graph, wiring, vdr-gate, ma, saas-metrics, pmi-planner]
dependency_graph:
  requires:
    - SaaSMetricsAgent at src/orchestra_tprm/agents/specialists/saas_metrics.py (Plan 01-04)
    - PMIPlannerAgent at src/orchestra_tprm/agents/pmi_planner.py (Plan 01-05)
    - Finding with ic_decision/workstream/exposure_usd_range (Plan 01-01)
    - ma_scope in RunRequest + initial graph state (Plan 01-01)
    - SpecialistModels.saas_metrics field in config.py (Plan 01-01)
  provides:
    - SaaSMetricsAgent node in M&A specialist parallel fan-out
    - vdr_gate node between intake and router (M&A only)
    - pmi_planner node after coordinator (M&A only)
    - _KIND_TO_AGENT_NAMES routing financial docs to SaaSMetricsAgent
    - _NODE_LABELS + _MA_PIPELINE updated in app.py
    - SSE verdict event carries ic_memo and pmi_plan
  affects:
    - PolicyAgent (Plan 01-03) — receives saas-metric findings from SaaSMetricsAgent via parallel fan-out
    - Coordinator (Plan 01-07) — pmi_plan and ic_memo now available in state after pmi_planner runs
    - Dashboard (Plan 01-08) — SSE verdict event now ships ic_memo and pmi_plan
tech_stack:
  added: []
  patterns:
    - Declarative graph branching on cfg.output_kind (no mode-string literals)
    - Keyword-match DRL completeness gate emitting informational Findings
    - Shim pattern for non-specialist callable agents wired as graph nodes
    - Lazy import for optional specialist (mirrors FinancialAgent pattern)
key_files:
  created: []
  modified:
    - src/orchestra_tprm/graph.py
    - src/orchestra_tprm/server/app.py
    - tests/tprm/integration/conftest.py
    - tests/tprm/integration/test_ma_mode.py
decisions:
  - ma_scope initial-state propagation was already present from Plan 01-01; no changes needed in _execute_graph_task
  - VDR gate emits findings via state_updates findings key using merge_list semantics — no blocking
  - Integration test scripted LLM responses updated to account for FinancialAgent QoE pass (second LLM call) + SaaSMetricsAgent + PMIPlannerAgent
metrics:
  duration: "~15 minutes"
  completed: "2026-05-18T02:20:00Z"
  tasks_completed: 3
  tasks_total: 3
---

# Phase 01 Plan 06: Graph Wiring Summary

Full M&A graph topology wired: SaaSMetricsAgent registered as parallel specialist, VDR completeness gate inserted between intake and router (M&A only), PMIPlannerAgent inserted after coordinator (M&A only), ma_scope propagated through to initial state, SSE verdict event extended with ic_memo and pmi_plan.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Wire SaaSMetricsAgent into _build_specialists and _KIND_TO_AGENT_NAMES | d771863 | graph.py |
| 2 | Add PMIPlanner node + VDR completeness gate to build_graph (M&A only) | ba93572 | graph.py |
| 3 | Propagate ma_scope into graph initial state + update NODE_LABELS / MA_PIPELINE | dd05246 | app.py |
| fix | Update integration test scripted LLM responses for new graph nodes (Rule 1) | 9275e23 | conftest.py, test_ma_mode.py |

## What Was Built

### Final M&A Graph Topology

```
bootstrap
    |
  intake
    |
 vdr_gate  <-- M&A only: DRL completeness check, emits informational findings
    |
  router   <-- LLM-driven document-to-specialist assignment
    |
  +---------+---------+-----------+-----------+-----------+
  |         |         |           |           |           |
legal   security  external     code      financial   saas_metrics
  |         |         |           |           |           |
  +---------+---------+-----------+-----------+-----------+
                        |
                      policy  <-- IC classification
                        |
                   coordinator  <-- Deal memo / report
                        |
                   pmi_planner  <-- M&A only: 100-day integration plan
                        |
                       END
```

### Final Vendor Graph Topology (unchanged)

```
bootstrap -> intake -> router -> [legal, security, external, code] (parallel) -> policy -> coordinator -> END
```

### The 3 cfg.output_kind == "doc" Conditionals

All three conditionals in `build_graph` branch exclusively on `cfg.output_kind`:

```python
# 1. VDR gate insertion
if cfg.output_kind == "doc":
    g.add_node("vdr_gate", ...)
    g.add_edge("intake", "vdr_gate")
    g.add_edge("vdr_gate", "router")
else:
    g.add_edge("intake", "router")

# 2. PMI planner insertion
if cfg.output_kind == "doc":
    pmi_planner = PMIPlannerAgent(model=cfg.coordinator_model)
    g.add_node("pmi_planner", ...)
    g.add_edge("coordinator", "pmi_planner")
    g.add_edge("pmi_planner", END)
else:
    g.add_edge("coordinator", END)
```

No mode-string literals (`if mode == "ma"` or `state.get("mode") == "ma"`) were introduced in graph.py.

### _DRL_CATEGORIES Table + Keyword Matching Strategy

The VDR gate checks 6 standard M&A DRL categories against document `path` and `kind` fields:

| Category | Keywords (any match = category present) |
|----------|-----------------------------------------|
| financial_statements | financial, 10-k, 10k, income, balance-sheet, p&l, annual |
| legal_corporate | articles, bylaws, incorporation, corporate, minutes, consent |
| ip_assignments | ip-assignment, ip_assignment, patent, trademark, copyright, invention |
| security_pentest | pentest, pen-test, penetration, soc2, soc-2, iso27001, iso-27001 |
| cap_table | cap-table, captable, cap_table, shareholder, equity-grant, option-grant |
| tax_returns | tax-return, tax_return, 1120, k-1, form-1120, irs |

Strategy: For each manifest entry, concatenate `path.lower() + "|" + kind.lower()` into a haystack string, then substring-search all keywords. One informational `Finding` per missing category: `severity="low"`, `workstream="legal"`, `ic_decision="post-close-monitoring"`. Run is never blocked.

### ma_scope Plumbing Chain

```
POST /run body (JSON)
    |
    v
RunRequest.ma_scope: dict | None  (Plan 01 added this field)
    |
    v
_execute_graph_task(... ma_scope: dict | None)  (Plan 01 added this kwarg)
    |
    v
initial: dict[str, Any] = {
    "mode": cfg.name,
    "subject_name": subject_name,
    "packet_path": packet_path,
    "ma_scope": ma_scope,   <-- key passed into compiled.run(input=initial)
}
    |
    v
graph state["ma_scope"]
    |
    +--> PolicyAgent._build_ic_memo (Plan 03) reads state["ma_scope"]
    +--> FinancialAgent QoE pass (Plan 02) reads state["ma_scope"]
    +--> PMIPlannerAgent (Plan 05) reads via ctx.state["ma_scope"]
```

### SSE Verdict Event Additions

The `verdict` SSE event now carries two new fields alongside existing fields:

```python
await queue.put(_sse("verdict", {
    "policy_verdict": verdict,
    "risk_score": risk_score,
    "findings_count": len(findings),
    "findings": findings,
    "verdict_doc_id": final_state.get("verdict_doc_id", ""),
    "verdict_local_path": final_state.get("verdict_local_path", ""),
    "ic_memo": final_state.get("ic_memo"),   # NEW: ICMemo model dump | None
    "pmi_plan": final_state.get("pmi_plan"), # NEW: PMIPlan model dump | None
}))
```

These are consumed by the dashboard (Plan 08) to render the IC memo section and PMI plan section.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Integration test ScriptedLLM exhausted by new graph nodes**

- **Found during:** Task 3 verification
- **Issue:** Integration tests used a ScriptedLLM fixture with exactly 7 scripted responses for the M&A flow. Adding SaaSMetricsAgent (1 new LLM call) and PMIPlannerAgent (1 new LLM call) to the graph caused ScriptedLLM to exhaust after 9 calls (FinancialAgent also makes a 2nd QoE pass call in M&A mode).
- **Fix:** Added 3 new responses to `_ma_responses()` in `conftest.py`: FinancialAgent QoE pass response, SaaSMetricsAgent response, PMIPlannerAgent response. Updated inline `ma_llm` in `test_ma_mode_uses_pro_model_for_long_context` identically.
- **Files modified:** `tests/tprm/integration/conftest.py`, `tests/tprm/integration/test_ma_mode.py`
- **Commit:** 9275e23

**2. ma_scope propagation already present (no-op)**

- Plan 01-01 already added `ma_scope` kwarg to `_execute_graph_task` and `"ma_scope": ma_scope` to the `initial` dict. Task 3 action item 3 was verified as already present — no additional changes were needed.

## Known Stubs

None — all new nodes are fully wired and functional. The SaaSMetricsAgent, VDRGate, and PMIPlannerAgent all execute in the live graph. The only constraint is that all three require documents in the VDR (or use their no-docs/empty fallbacks).

## Threat Flags

None — no new network endpoints, auth paths, or file access patterns introduced. The VDR gate reads from `state["packet_manifest"]` (internal state) and the new graph nodes follow the same execution boundary as existing nodes.

## Self-Check: PASSED

- `src/orchestra_tprm/graph.py` — FOUND (SaaSMetricsAgent lazy import, _build_specialists, _KIND_TO_AGENT_NAMES, _DRL_CATEGORIES, _vdr_completeness_check, _make_vdr_gate_shim, _make_pmi_planner_shim, cfg.output_kind conditionals)
- `src/orchestra_tprm/server/app.py` — FOUND (_NODE_LABELS updated, _MA_PIPELINE explicit, SSE verdict extended)
- `tests/tprm/integration/conftest.py` — FOUND (10-response scripted LLM for M&A flow)
- `tests/tprm/integration/test_ma_mode.py` — FOUND (inline ma_llm updated)
- Commit d771863 — FOUND (Task 1: SaaSMetricsAgent wiring)
- Commit ba93572 — FOUND (Task 2: VDR gate + PMI planner)
- Commit dd05246 — FOUND (Task 3: NODE_LABELS + MA_PIPELINE + SSE verdict)
- Commit 9275e23 — FOUND (Rule 1 fix: integration test scripted LLM)
- `python -m pytest tests/tprm/unit/ -x -q` — 233 passed
- `python -m pytest tests/tprm/integration/ -x -q` — 5 passed
- No mode-string literals in graph.py verified
