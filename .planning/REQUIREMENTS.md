# Requirements — TPRM M&A Due Diligence Enhancement

## Phase 1 Requirements

### Scoping & Preparation (Phase 1 of 4-phase model)

**REQ-01** (Phase 1): Pre-run scoping screen UI
- Capture: investment thesis text, enterprise value ($), materiality threshold (default 1-2% of EV), deal-breaker conditions (freeform list), active workstreams toggle
- Store as `MAScope` model passed to all agents
- Dashboard form rendered before POST /run in M&A mode

**REQ-02** (Phase 1): VDR completeness gate [DONE - Plan 01-06]
- Before specialists run, check uploaded documents against standard DRL categories: financial statements, legal/corporate docs, IP assignments, pen test report, cap table, tax returns
- Warn (not block) if categories are missing; surface as pre-run findings
- Missing categories logged as `severity: informational` findings with `ic_decision: post-close-monitoring`

### Schema Changes

**REQ-03** (Phase 1): Extend `Finding` schema in `schemas.py`
- Add `exposure_usd_range: tuple[int, int] | None = None` — estimated financial exposure range in USD
- Add `ic_decision: Literal["deal-stopper", "price-adjustment", "SPA-protection", "post-close-monitoring"] | None = None`
- Add `workstream: Literal["legal", "financial", "tech", "commercial", "hr", "esg", "regulatory"] | None = None`
- `id: str` field already exists (UUID4 default factory from prior work)

**REQ-04** (Phase 1): New `MAScope` model in `schemas.py`
- Fields: `investment_thesis: str`, `enterprise_value_usd: int | None`, `materiality_threshold_usd: int | None`, `deal_breakers: list[str]`, `active_workstreams: list[str]`
- Passed into `RunRequest` as `ma_scope: MAScope | None = None`

**REQ-05** (Phase 1): New output schemas
- `ICMemo`: `executive_summary: str`, `headline_terms: str`, `recommendation: Literal["proceed", "reprice", "walk"]`, `risk_register: list[ICRiskItem]`
- `ICRiskItem`: `finding_id: str`, `workstream: str`, `exposure_usd_range: tuple[int,int] | None`, `mitigation: Literal["price-chip", "indemnity", "escrow", "RWI", "earn-out", "CP", "post-close"]`, `probability: Literal["low", "medium", "high"]`
- `PMIPlan`: `summary: str`, `items: list[PMIItem]`
- `PMIItem`: `workstream: str`, `action: str`, `deadline_tier: Literal["day-30", "day-60", "day-100", "day-180"]`, `owner: str`, `dependency: str | None`

### Agent Changes

**REQ-06** (Phase 1): FinancialAgent QoE normalization
- Add EBITDA normalization pass: identify one-time items, owner compensation excess, related-party transactions, non-recurring revenue, capitalized vs expensed R&D, SaaS deferred revenue haircut
- Compute `qoe_adjusted_ebitda` and `ebitda_chip_usd` (reported minus adjusted × agreed multiple from `MAScope.enterprise_value_usd`)
- Working capital peg methodology: 12-month average excluding cash, debt, deal-related accruals
- Output normalized findings with `workstream: "financial"` and `exposure_usd_range` populated

**REQ-07** (Phase 1): New SaaS metrics agent (`agents/specialists/saas_metrics.py`)
- Parallel specialist (runs alongside other specialists in M&A mode only)
- Extracts: ARR, NRR/NDR, GRR, CAC payback, LTV:CAC, logo retention, cohort churn, Rule of 40
- Red-flag thresholds: NRR < 100% → price-adjustment, NRR < 90% → deal-stopper; logo retention < 85% → deal-stopper; Rule of 40 < 20 → price-adjustment
- SaaS-specific flags: single-version lock, API contract concentration > 40% ARR, metered billing anomalies, seat vs usage revenue mix
- Output: `list[Finding]` with `workstream: "financial"`, `ic_decision` populated per threshold

**REQ-08** (Phase 1): CodeAgent OSS license check
- Add OSS license contamination pass to existing `code.py`
- GPL/AGPL in commercial product → `severity: critical`, `ic_decision: "deal-stopper"`, `exposure_usd_range: (0, enterprise_value_usd)` (product may be unlicensable)
- LGPL in commercial product → `severity: high`, `ic_decision: "SPA-protection"`
- Permissive (MIT/Apache/BSD) → `severity: low`, `ic_decision: "post-close-monitoring"`
- Output findings with `workstream: "tech"`

**REQ-09** (Phase 1): PolicyAgent 4-way IC classification
- Replace current RAG verdict with IC decision framework
- Deal-stopper: unquantifiable exposure OR deal-breaker threshold from `MAScope` triggered
- Price-adjustment: quantifiable EBITDA/ARR impact > materiality threshold
- SPA-protection: ring-fence via specific indemnity/warranty for known bounded risk
- Post-close monitoring: immaterial or manageable risk < materiality threshold
- Output `ICMemo` schema (REQ-05)

### New Agents

**REQ-10** (Phase 1): PMI Planner agent (`agents/pmi_planner.py`)
- Runs after coordinator, M&A mode only
- Input: all findings with `workstream` and `ic_decision` populated
- Maps findings to integration actions with deadline tiers (Day 30/60/100/180)
- Tech DD findings → IT integration workstreams
- HR findings → retention package actions
- Legal findings → Day-1 legal entity actions
- Output: `PMIPlan` schema (REQ-05)

### Frontend Changes

**REQ-11** (Phase 1): Scoping screen component in dashboard
- Rendered before run in M&A mode (SourceToggle already distinguishes modes)
- Fields: investment thesis (textarea), EV ($, optional), materiality threshold ($ with default 2% of EV), deal-breaker conditions (tag input), workstream toggles
- Submit populates `ma_scope` in POST /run body
- Skip button available (all fields optional)

**REQ-12** (Phase 1): Updated findings table
- Add columns: `Workstream` (badge), `Exposure Range` ($X–$Y or "—"), `IC Decision` (colored chip: red=deal-stopper, orange=price-adj, yellow=SPA, green=post-close)
- IC Decision chips replace the existing severity-only display
- Findings grouped by workstream when in M&A mode

**REQ-13** (Phase 1): IC memo section in results
- Rendered after VerdictCard in M&A mode
- Shows: recommendation (proceed/reprice/walk), executive summary, risk register table
- Risk register: workstream | description | exposure range | mitigation type

**REQ-14** (Phase 1): PMI 100-day plan section
- Rendered at bottom of results in M&A mode after IC memo
- Timeline grouped by deadline tier (Day 30 / Day 60 / Day 100 / Day 180)
- Each item shows workstream badge + action + owner

### Output Artifacts

**REQ-15** (Phase 1): Restructure coordinator Google Doc for M&A mode
- Sections: Executive Summary → IC Memo → Workstream Reports (one per active workstream) → Risk Register → PMI 100-Day Plan → Appendix (full findings list)
- Each workstream section: findings count by IC decision, top 3 findings detail, workstream-specific recommendations
- Replace flat findings dump with structured workstream-organized report
