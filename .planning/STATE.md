# Project State — Orchestra TPRM M&A Enhancement

**Project:** Orchestra TPRM — M&A Due Diligence Mode
**Code:** TPRM-MA
**Status:** In Progress
**Last Activity:** 2026-05-18
**Plan 01-05 Duration:** ~3 min
**Plan 01-06 Duration:** ~15 min
**Plan 01-07 Duration:** ~5 min
**Plan 01-08 Duration:** ~6 min
**Last Completed:** Plan 01-08 (M&A Dashboard UI — ScopingScreen, ICMemoSection, PMIPlanSection)
**Current Phase:** 01 — M&A Due Diligence Mode Enhancement
**Current Position:** Wave 6 / Plan 01-09 (final plan)

## Phase Status

| Phase | Name | Status | Plans |
|-------|------|--------|-------|
| 1 | M&A Due Diligence Mode Enhancement | In Progress | 9 |

## Key Decisions

- M&A mode redesign scope: full 4-phase workflow imitation (Preparation → Execution → Synthesis → Integration Planning)
- Research complete: 2× Sonnet research runs + Google AI search result on real M&A DD workflows
- Schema-first approach: extend Finding with `exposure_usd_range`, `ic_decision`, `workstream` before agent changes
- New agents: SaaS metrics specialist (parallel), PMI Planner (post-coordinator)
- PolicyAgent replaced with IC classification (4-way: deal-stopper/price-adjustment/SPA-protection/post-close)
- Frontend: scoping screen + updated findings table + IC memo section + PMI plan section
- Coordinator Google Doc restructured into workstream-organized sections
- Deadline: 2026-05-19 08:00 SGT (hackathon submission)
- Plan 01-01: Use dict|None for RunRequest.ma_scope to avoid circular import between app.py and schemas.py
- Plan 01-01: Fix Gemini schema converter to convert tuple prefixItems to array (not raise) for Gemini compatibility
- Plan 01-02: QoE pass only fires when mode=ma AND all_findings non-empty; implied multiple capped at 20x, default 8x
- Plan 01-02: OSS license allowlist includes APACHE-2.0, BSD-3-CLAUSE, BSD-2-CLAUSE (SPDX variants) to avoid false positives
- Plan 01-03: ICMemo placeholder emitted in vendor mode (empty, recommendation=proceed) so ic_memo never None in state
- Plan 01-03: ma_scope presence (not mode string) gates IC classification; vendor mode YAML verdict unchanged
- Plan 01-04: No-docs fallback emits informational Finding (audit trail) rather than silent [] when VDR lacks financial docs
- Plan 01-04: ic_decision clamping to known 4-value set prevents Pydantic validation errors from LLM label drift
- Plan 01-05: PMIPlannerAgent uses callable-agent pattern (not BaseTPRMAgent subclass); unknown tiers clamped to day-100; unknown workstreams filtered out
- Plan 01-05: Deterministic fallback encodes all 4 deadline tiers from CONTEXT.md without LLM dependency
- Plan 01-06: All graph branching by cfg.output_kind only (no mode-string literals in graph.py)
- Plan 01-06: VDR gate uses keyword-match strategy (path|kind haystack) for 6 DRL categories; emits low-severity informational findings only
- Plan 01-06: ma_scope propagation was already present from Plan 01-01; Task 3 verified and extended SSE verdict event with ic_memo + pmi_plan
- Plan 01-06: Integration test scripted LLM needed 10 responses (router + 6 parallel specialists + coordinator + pmi_planner + FinancialAgent QoE second call)
- Plan 01-07: LLM narrative scoped to Executive Summary only; all other 5 sections rendered from structured state (ic_memo, pmi_plan, findings)
- Plan 01-07: Workstream Reports alphabetically ordered; top-3 findings per section by severity; findings without workstream tag grouped under 'general'
- Plan 01-07: PMI tier canonical order: day-30 -> day-60 -> day-100 -> day-180 (encoded in _PMI_TIER_ORDER tuple)
- Plan 01-08: ScopingScreen shown as pre-run card in M&A mode; gated behind (mode==="vendor" || scopingComplete); changeMode() resets scopingComplete on mode switch
- Plan 01-08: VerdictCard extended with mode prop for 7-column M&A table vs 4-column vendor table
- Plan 01-08: IC_COLOR palette locked to CONTEXT.md values; WS_COLOR uses Google-palette compliant hex values
- Plan 01-08: ICMemoSection/PMIPlanSection rendered after VerdictCard gated on rs.mode==="ma" and data presence
