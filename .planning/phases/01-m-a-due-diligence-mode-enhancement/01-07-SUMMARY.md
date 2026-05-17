---
phase: 01-m-a-due-diligence-mode-enhancement
plan: "07"
subsystem: agents
tags: [coordinator, google-doc, ma, 6-section-layout, render-helpers]
dependency_graph:
  requires:
    - ICMemo model in schemas.py (Plan 01-01)
    - PMIPlan/PMIItem models in schemas.py (Plan 01-01)
    - Finding with ic_decision/workstream/exposure_usd_range (Plan 01-01)
    - ic_memo in state via PolicyAgent (Plan 01-03)
    - pmi_plan in state via PMIPlannerAgent (Plan 01-05)
    - PMIPlannerAgent wired after coordinator in graph (Plan 01-06)
  provides:
    - Coordinator._write_doc restructured into 6 ordered sections
    - _render_workstream_section (workstream -> text block, top-3 severity)
    - _render_risk_register (ICMemo -> text table)
    - _render_pmi_plan (PMIPlan -> tier-grouped text)
    - _coerce_ic_memo / _coerce_pmi_plan (defensive dict->model coercion)
    - _PMI_TIER_ORDER constant ("day-30", "day-60", "day-100", "day-180")
  affects:
    - Dashboard (Plan 01-08) — Google Doc section order now deterministic and structured
tech_stack:
  added: []
  patterns:
    - Module-level render helpers (pure functions, no class state)
    - Defensive Pydantic coercion at state boundary (dict or model instance)
    - Alphabetical workstream ordering for deterministic section sequence
    - cfg.output_kind dispatch preserved (no mode-string literals added)
key_files:
  created: []
  modified:
    - src/orchestra_tprm/agents/coordinator.py
    - tests/tprm/unit/test_coordinator.py
decisions:
  - "LLM narrative scoped to Executive Summary only; structured state drives all other 5 sections"
  - "Workstream Reports alphabetically ordered for deterministic doc layout"
  - "Top-3 findings per workstream sorted by severity (critical > high > medium > low)"
  - "Risk register sourced exclusively from ICMemo.risk_register (not raw findings)"
  - "PMI plan tiers rendered in canonical order: day-30 -> day-60 -> day-100 -> day-180"
  - "Findings without workstream tag grouped under 'general' bucket"
  - "test_ma_coordinator_creates_doc_with_sections updated to match new 6-section layout (Rule 1 fix)"
metrics:
  duration: "~5 minutes"
  completed: "2026-05-18T18:27:00Z"
  tasks_completed: 1
  tasks_total: 1
---

# Phase 01 Plan 07: Coordinator Google Doc 6-Section Layout Summary

Restructured `Coordinator._write_doc` to emit a deterministic 6-section dict in the locked CONTEXT.md order, consuming `ic_memo` and `pmi_plan` from graph state. The LLM narrative is scoped to the Executive Summary only; all other sections are rendered from structured Pydantic models.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Restructure Coordinator._write_doc into the locked 6-section layout | 5ee6f16 | coordinator.py, test_coordinator.py |

## What Was Built

### 6-Section Render Order (Verbatim from CONTEXT.md)

```
1. Executive Summary      — LLM narrative (or parsed "Executive Summary" key from JSON response)
2. IC Memo                — ICMemo.recommendation + headline_terms + executive_summary
3. Workstream Reports     — One block per workstream, alphabetical, top-3 findings by severity
4. Risk Register          — ICMemo.risk_register as text table
5. PMI 100-Day Plan       — PMIPlan items grouped by deadline tier (day-30 first)
6. Appendix: Full Findings — JSON dump of all Finding objects
```

### Workstream Grouping Logic

Findings are grouped into `ws_map: dict[str, list[Finding]]` using `f.workstream or "general"` as the key. Workstreams are rendered alphabetically (`sorted(ws_map.keys())`).

Per workstream, `_render_workstream_section` produces:
- Header: `Workstream: {ws.title()}`
- Count summary: IC decision label counts (alphabetical)
- Top 3 findings by severity (critical=0, high=1, medium=2, low=3), with exposure range if set

### Risk Register Table Column Order

```
Finding ID | Workstream | Exposure (USD) | Mitigation | Probability
---------- | ---------- | -------------- | ---------- | -----------
{id}       | {ws}       | ${low}–${high} | {mit}      | {prob}
```

Exposure shows `—` when `exposure_usd_range is None`. Table sourced from `ICMemo.risk_register` only.

### PMI Plan Tier Ordering Constant

```python
_PMI_TIER_ORDER = ("day-30", "day-60", "day-100", "day-180")
```

`_render_pmi_plan` iterates this tuple in order, skipping tiers with no items. Each tier is headed by `## {tier.upper()}`. Items show `[workstream] action — owner: {owner} (depends on: {dep})`.

### ICMemo / PMIPlan Defensive Coercion Helpers

```python
def _coerce_ic_memo(raw: Any) -> ICMemo | None:
    # Handles: None -> None, ICMemo -> passthrough, dict -> ICMemo(**raw)

def _coerce_pmi_plan(raw: Any) -> PMIPlan | None:
    # Handles: None -> None, PMIPlan -> passthrough, dict -> PMIPlan(**raw)
```

Both use `except Exception: return None` to handle malformed state without crashing. State values from the graph arrive as dicts (serialised via `model_dump()`), so coercion is always required.

### Vendor Mode `_write_sheet` Unchanged

The `_write_sheet` method (lines 217-255) was not touched. The `__call__` dispatch (`dispatch = {"sheet": self._write_sheet, "doc": self._write_doc}`) also unchanged. No mode-string literals were introduced.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_ma_coordinator_creates_doc_with_sections expected old free-text sections**

- **Found during:** Task 1 verification
- **Issue:** The existing unit test checked for `"Strategic Fit"`, `"Financial Analysis"`, `"Risks"` in the doc body — headings from the old `_ma_sections_from_text` free-text parsing path. The new `_write_doc` ignores those narrative-embedded headings (only uses `"Executive Summary"` from the parsed LLM response). The test failed with `AssertionError: Section 'Strategic Fit' missing from deal memo body`.
- **Fix:** Updated `test_ma_coordinator_creates_doc_with_sections` to: (a) provide `ic_memo` and `pmi_plan` in state, (b) use a plain narrative string (not JSON sections), (c) assert all 6 locked heading names appear in the body, (d) assert structural content (`PROCEED`, `DAY-30`, `indemnity`) is rendered correctly.
- **Files modified:** `tests/tprm/unit/test_coordinator.py`
- **Commit:** 5ee6f16 (same commit as implementation)

## Known Stubs

None — all 6 sections are fully wired to real state data. The `ic_memo` and `pmi_plan` keys arrive from PolicyAgent (Plan 03) and PMIPlannerAgent (Plan 05) respectively, both of which produce non-None output in M&A mode.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced. `_write_doc` reads from internal graph state only, and the DocsAdapter call path is unchanged.

## Self-Check: PASSED

- `src/orchestra_tprm/agents/coordinator.py` — exists
  - `from orchestra_tprm.schemas import Finding, ICMemo, PMIPlan` — 1 match
  - `def _render_workstream_section` — 1 match
  - `def _render_risk_register` — 1 match
  - `def _render_pmi_plan` — 1 match
  - `def _coerce_ic_memo` — 1 match
  - `def _coerce_pmi_plan` — 1 match
  - `_PMI_TIER_ORDER` — 2 matches (definition + use in `_render_pmi_plan`)
  - `"Executive Summary"` — 3 matches (parsed_narrative.get, sections key, return annotation)
  - `"IC Memo"` — 2 matches
  - `"Workstream Reports"` — 1 match
  - `"Risk Register"` — 1 match
  - `"PMI 100-Day Plan"` — 1 match
  - `"Appendix: Full Findings"` — 1 match
  - No `if mode == "ma"` — 0 matches
  - No `state.get("mode") == "ma"` — 0 matches
- `tests/tprm/unit/test_coordinator.py` — updated with 6-section assertions
- Commit 5ee6f16 — FOUND (feat(01-07): restructure Coordinator._write_doc)
- `python -m pytest tests/tprm/unit/ -x -q` — 233 passed
