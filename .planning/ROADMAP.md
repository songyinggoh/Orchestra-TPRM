# Orchestra TPRM — M&A Enhancement Roadmap

## Project
**Name:** Orchestra TPRM — M&A Due Diligence Mode
**Code:** TPRM-MA
**Goal:** Transform the TPRM M&A mode from a label-swapped vendor review into an authentic M&A due diligence workflow that matches how real deal teams operate.

---

## Phase Summary

- [ ] **Phase 1: M&A Due Diligence Mode Enhancement** — Full redesign of M&A mode: scoping screen, SaaS metrics, QoE normalization, IC memo output, PMI plan, workstream-organized artifacts

---

## Phase 1: M&A Due Diligence Mode Enhancement

**Goal:** Redesign the TPRM M&A mode to authentically imitate real M&A due diligence — a 4-phase workflow (Preparation → Execution → Synthesis → Integration Planning) with per-workstream artifacts, quantified findings, IC memo output, and a PMI 100-day plan.

**Plan Progress:**

| Plan | Name | Status |
|------|------|--------|
| 01-01 | M&A Schema Foundation | DONE (c6abfd6, b32ab28) |
| 01-02 | FinancialAgent QoE + CodeAgent OSS | DONE (26651e7, 4a62317) |
| 01-03 | PolicyAgent IC classification | DONE (cec952e) |
| 01-04 | SaaSMetricsAgent | DONE (c09d5b8, bb1e41a) |
| 01-05 | PMI Planner agent | Pending |
| 01-06 | Coordinator wiring | Pending |
| 01-07 | Google Doc restructure | Pending |
| 01-08 | Frontend scoping + IC memo + PMI | Pending |
| 01-09 | Integration tests | Pending |

**Success Criteria**:
1. Pre-run scoping screen captures investment thesis, enterprise value, materiality threshold, and deal-breaker conditions before any specialist runs
2. VDR completeness gate checks for missing document categories and warns before execution
3. PolicyAgent produces 4-way IC classification (deal-stopper / price-adjustment / SPA-protection / post-close-monitoring) with quantified exposure range, not just RAG verdict
4. Finding schema includes `exposure_usd_range` and `ic_decision` fields populated by all specialists
5. FinancialAgent performs QoE EBITDA normalization with standard add-back categories and deferred revenue haircut for SaaS targets
6. SaaS metrics agent checks NRR, GRR, logo retention, CAC payback, Rule of 40 with documented red-flag thresholds
7. CodeAgent includes OSS license contamination check with deal-stopper flag for GPL/AGPL in commercial product
8. Google Doc output restructured into workstream sections (Legal, Financial/QoE, Tech DD, Commercial, HR, ESG) + IC memo section
9. PMI 100-day plan generated as Phase 4 output artifact with 30/60/100-day tier assignments per integration workstream
10. All existing pytest unit tests continue to pass after schema and agent changes
