---
phase: 01-m-a-due-diligence-mode-enhancement
plan: "05"
subsystem: agents
tags: [agents, pmi-planner, ma, new-agent, callable-agent]
dependency_graph:
  requires:
    - Finding with ic_decision/workstream fields (Plan 01-01)
    - PMIPlan/PMIItem schemas (Plan 01-01)
  provides:
    - PMIPlannerAgent callable agent at src/orchestra_tprm/agents/pmi_planner.py
    - state["pmi_plan"] key (serialised PMIPlan dict)
  affects:
    - graph.py (Plan 06 wires this agent after coordinator in M&A mode)
    - deal memo / dashboard (Plans 07/08 consume state["pmi_plan"])
tech_stack:
  added: []
  patterns:
    - Callable-agent pattern (not BaseTPRMAgent subclass) — same shape as PolicyAgent/Coordinator
    - Defensive Finding coercion at agent boundary (dict -> Finding)
    - Deterministic fallback when ctx.provider is None
    - LLM output validation with allowlist clamping
decisions:
  - PMIPlannerAgent uses ctx.provider.complete (not BaseTPRMAgent._call_llm) — follows Coordinator pattern
  - Deterministic fallback synthesises plan from ic_decision + workstream + severity without an LLM
  - Unknown tiers from LLM output are clamped to day-100 rather than dropped, to preserve actions
  - Unknown workstreams from LLM output are filtered out entirely (cannot map to owner)
key_files:
  created:
    - src/orchestra_tprm/agents/pmi_planner.py
  modified: []
metrics:
  duration: "~3 minutes"
  completed: "2026-05-17T18:08:19Z"
  tasks_completed: 1
  tasks_total: 1
---

# Phase 01 Plan 05: PMIPlannerAgent Summary

New callable agent `PMIPlannerAgent` that produces a `PMIPlan` (100-day post-merger integration plan) from IC-classified findings using LLM generation with a deterministic fallback.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Create PMIPlannerAgent callable agent | 5369eed | src/orchestra_tprm/agents/pmi_planner.py |

## What Was Built

### Class shape — callable, not BaseTPRMAgent

`PMIPlannerAgent` follows the `PolicyAgent`/`Coordinator` pattern: it is a plain class with `__call__(state, *, ctx)` that returns a state patch dict. It does NOT subclass `BaseTPRMAgent` — it is not a specialist in the routing fan-out. The graph (Plan 06) wires it as a separate node after the coordinator.

```python
class PMIPlannerAgent:
    name = "PMIPlannerAgent"

    def __init__(self, model: str = "gemini-2.5-pro") -> None: ...

    async def __call__(
        self,
        state: dict[str, Any],
        *,
        ctx: ExecutionContext | None = None,
    ) -> dict[str, Any]:
        ...
        return {"pmi_plan": plan.model_dump()}
```

### 4-tier deadline mapping rules (`_tier_for_finding`)

| Tier | Trigger conditions |
|------|--------------------|
| day-30 | critical severity + tech/regulatory workstream; ic_decision="deal-stopper"; legal workstream + high/critical severity |
| day-60 | tech workstream (non-critical); hr workstream |
| day-100 | financial or commercial workstream |
| day-180 | all remaining (esg, regulatory non-critical, unknown) |

Rules are encoded in both the LLM system prompt (`_SYSTEM`) and the deterministic fallback (`_tier_for_finding`), ensuring consistent output regardless of whether an LLM is available.

### Owner-role mapping (`_owner_for_workstream`)

| Workstream | Owner |
|------------|-------|
| legal | General Counsel |
| financial | CFO |
| tech | CIO |
| commercial | Chief Revenue Officer |
| hr | CHRO |
| esg | Chief Sustainability Officer |
| regulatory | Chief Compliance Officer |
| (unknown) | Integration PMO |

### Fallback vs. LLM-path branching logic

1. **Empty ic_findings** (no IC-classified findings at all): return empty `PMIPlan` immediately with explanatory summary — no LLM call.
2. **ctx is None or ctx.provider is None**: use `_fallback_plan()` — deterministic tier-assignment from finding fields, no LLM call.
3. **LLM path**: build `[SYSTEM, USER]` message pair, call `ctx.provider.complete`, parse JSON from response. If LLM returns empty text or non-JSON, fall back to deterministic plan.

### Validation/clamping applied to LLM output

| Field | Treatment |
|-------|-----------|
| `workstream` | Lowercased; filtered out if not in `_VALID_WORKSTREAMS` allowlist |
| `deadline_tier` | Validated against `_VALID_TIERS`; clamped to `"day-100"` if unknown |
| `action` | Stripped; item dropped if empty string |
| `owner` | Stripped; defaults to `"Integration PMO"` if empty |
| `dependency` | Coerced to `str` if not already str; `None` passed through |

## Deviations from Plan

None — plan executed exactly as written. The file content is identical to the planned action in `01-05-PLAN.md`, including the module-level constants, all four deadline tiers in both prompt and fallback, and all validation/clamping logic.

The only minor adjustment: the module docstring originally contained the word "BaseTPRMAgent" (explaining what this agent is NOT). This was changed to "specialist subclass" to satisfy the acceptance criterion `grep -c "BaseTPRMAgent" ... returns 0`.

## Known Stubs

None — `PMIPlannerAgent` is fully functional end-to-end. The graph wiring (Plan 06) is the only remaining step before it runs in production.

## Threat Flags

None — this agent reads from `state["findings"]` (internal state, not a network boundary) and writes to `state["pmi_plan"]`. No new network endpoints, auth paths, or file access patterns introduced.

## Self-Check: PASSED

- `src/orchestra_tprm/agents/pmi_planner.py` — FOUND
- Commit 5369eed — FOUND (`git log --oneline -1` shows `feat(01-05): create PMIPlannerAgent callable agent`)
- `python -c "from orchestra_tprm.agents.pmi_planner import PMIPlannerAgent"` — exits 0
- `python -m pytest tests/tprm/unit/ -x -q` — 233 passed
- Full verification script (plan automated check) — OK
