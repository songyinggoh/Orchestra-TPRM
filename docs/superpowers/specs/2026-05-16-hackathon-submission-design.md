# lablab.ai Hackathon Submission — Design

**Date:** 2026-05-16
**Deadline:** 2026-05-19 08:00 SGT (3 days)
**Track:** Transforming Enterprise Through AI — Track 2: AI Agents with Google AI Studio
**Status:** Draft — pending user approval

---

## 1. Context

We are submitting **Orchestra + TPRM** to the lablab.ai Track 2 hackathon. Orchestra is a Python multi-agent orchestration framework with 1,069 unit tests, full observability, and 7 LLM provider backends. TPRM (Third-Party Risk Management) is a flagship application built on Orchestra — a 5-specialist agent pipeline that ingests vendor packets, runs Legal, Security, Code, External, and Financial review against a policy pack, and produces a unified verdict.

The hackathon requires Google AI Studio / Gemini, which Orchestra already supports via `GoogleProvider`. The current TPRM live demo produces 33 findings across 4 specialists on a real HashiCorp vendor packet.

The submission story is dual-layered:
- **Orchestra** = the platform — production-grade multi-agent infrastructure
- **TPRM** = the proof — a concrete enterprise use case that ships

Judges score on Presentation, Business Value, Application of Technology, and Originality. We win by demonstrating that Orchestra makes real enterprise AI applications *fast to build*, and that TPRM is a $50K+/year category killer.

## 2. Goal

A submitted, public, judged-ready package containing:

1. Hosted, interactive demo URL (Cloud Run)
2. Public GitHub repo
3. 5-minute video presentation
4. PDF slide deck
5. Submission form filled (title, descriptions, tags, cover image)

The demo must execute a live vendor review during the judging window using real Gemini API calls and produce a Google Sheet/Doc artifact that judges can open.

## 3. Architecture

### 3.1 Deployment topology

```
                        ┌──────────────────────────────────┐
                        │       Cloud Run (single svc)      │
                        │                                   │
   judges browser ─────►│  FastAPI (orchestra-tprm)         │
                        │   ├── /api/v1/runs        (POST)  │
                        │   ├── /api/v1/runs/.../stream     │
                        │   ├── /api/v1/tprm/scorecard      │
                        │   └── /  (static React build)     │
                        │                                   │
                        └──────────────────────────────────┘
                                       │
                  ┌────────────────────┼─────────────────────┐
                  ▼                    ▼                     ▼
        generativelanguage      bigquery.googleapis    sheets/docs.googleapis
        .googleapis.com         .com                   .com
        (Gemini 2.5 Flash)      (findings table)       (sheet + doc output)
        AI Studio — free        Cloud Run SA           Cloud Run SA
```

- Single Cloud Run service serves FastAPI + static React build
- Gemini API via `GOOGLE_API_KEY` (Cloud Run secret) — AI Studio billing, free tier, no GCP credits consumed
- BigQuery + Sheets + Docs via Cloud Run service account with IAM roles
- Scales to zero between requests; cold start ~3–5s

### 3.2 Agent graph (TPRM, vendor mode)

```
intake ─► doc_router ─┬─► legal       ─┐
                      ├─► security    ─┤
                      ├─► code        ─┼─► risk_score ─┐
                      ├─► external    ─┤               │
                      ├─► (financial) ─┤               ├─► policy ─► remediation ─► coordinator ─► END
                      └─► esg         ─┘               │
                                                       │
                              all findings ────────────┘
```

New nodes (yellow): `esg`, `risk_score`, `remediation`.

`risk_score` runs after specialists join, before `policy`. `remediation` runs after `policy` so it can incorporate the verdict. `coordinator` produces the final Sheet/Doc.

### 3.3 Frontend

The existing React dashboard at `src/orchestra/ui/` is already production-grade:

- `useSSE` hook with backoff reconnect + `Last-Event-ID` resumability
- EventTimeline, NodeCard, CostDashboard, ScrubberBar, ForkComposer, StateViewer
- Full type definitions in `types/api.ts` matching Pydantic models
- Components from shadcn/ui + Tailwind

We add **TPRM-specific pages** without modifying generic Orchestra components:

- `/tprm` — landing page with mode selector (vendor / M&A), example chooser (Acme / HashiCorp), upload widget
- `/tprm/runs/:runId` — live run page with risk score hero card, findings table, remediation roadmap, Sheet/Doc link

## 4. Scope

### 4.1 In scope (this instance owns)

| # | Work item | Estimate |
|---|---|---|
| A | Fix 5 critical bugs from Day 4 review (CR-01 through CR-05) | 3h |
| B | Build 3 new agents: Risk Scoring, Remediation, ESG | 8h |
| C | TPRM-specific React pages (landing, run detail) | 6h |
| D | Cloud Run deployment config + GCP service account + IAM | 3h |
| E | Slide deck (PDF) | 3h |
| F | 5-minute video (script + record + edit) | 4h |
| G | Submission form content (title, descriptions, tags, cover image) | 2h |

**Total: ~29h across 3 days, 1 builder. Tight but feasible.**

### 4.2 Owned by other instance

| # | Work item | From other instance |
|---|---|---|
| 11 | Wire FastAPI `/run` and `/events/{run_id}` stubs to TPRM graph + SSE event emission | In progress |
| 12 | Replay mode + GitHub Actions CI workflow to Cloud Run | In progress |

We depend on #11 stabilizing the API surface (`POST /api/v1/runs` payload shape, SSE event types). Coordinate via the shared spec; do not edit FastAPI files in this instance until #11 lands.

### 4.3 Out of scope

- New TPRM modes beyond vendor + M&A
- Multi-tenant auth (single demo user is fine)
- Production observability (OpenTelemetry already wired in framework; judges won't see traces)
- BigQuery dashboards / Looker Studio
- Vendor packet ingestion via email or API (manual upload is fine for demo)
- Mobile UI

## 5. New Agents

All three follow the existing specialist pattern (`agents/specialists/<name>.py`), inherit from `SpecialistAgentBase`, return `list[Finding]` for ESG or a new typed schema for the others.

### 5.1 Risk Scoring Agent

**File:** `src/orchestra_tprm/agents/risk_score.py`

**Purpose:** Convert findings across specialists into a single 0–100 vendor risk score with traffic-light verdict.

**Position in graph:** After all specialists join, before `policy`.

**Input:** All `Finding` objects + active `PolicyPack` weights.

**Process:** Deterministic scoring (not LLM) — applies policy weights to each finding's severity, aggregates per dimension, normalizes to 0–100. Uses LLM only to generate a 1-sentence rationale for the top 3 risk drivers.

**Output schema:**
```python
class RiskScore(BaseModel):
    overall: int                          # 0-100, higher = riskier
    verdict: Literal["green", "amber", "red"]
    dimensions: dict[str, int]            # {"legal": 12, "security": 45, ...}
    top_risk_drivers: list[RiskDriver]    # at most 3
    explanation: str                      # 1-2 sentence rationale

class RiskDriver(BaseModel):
    dimension: str                        # "security"
    finding_id: str
    severity: Literal["medium", "high", "critical"]
    one_liner: str                        # "SOC2 CC6.1 control evidence is missing"
```

**Verdict thresholds (configurable per mode policy):**
- Green: overall ≤ 30 (vendor) / ≤ 20 (M&A)
- Amber: 31–69 (vendor) / 21–59 (M&A)
- Red: ≥ 70 (vendor) / ≥ 60 (M&A)

### 5.2 Remediation Agent

**File:** `src/orchestra_tprm/agents/remediation.py`

**Purpose:** Generate prioritized action plan from findings — transforms diagnostic output into a decision-support tool.

**Position in graph:** After `policy`. Skipped if `policy` verdict is `approve` with no medium-or-higher findings.

**Input:** All findings of severity ≥ medium, plus active mode (vendor / M&A) and policy verdict.

**Process:** Single LLM call (Gemini 2.5 Flash) with structured output. Mode-aware prompt: vendor mode frames remediation as "vendor must fix X before signing"; M&A mode frames as "negotiate price reduction, escrow, or rep-and-warranty insurance for X".

**Output schema:**
```python
class RemediationItem(BaseModel):
    finding_id: str
    action: str                           # imperative, specific
    owner: Literal["vendor", "buyer", "both"]
    priority: Literal["P0", "P1", "P2"]
    leverage: str                         # contract clause / cert / escrow term to use
    estimated_effort: Literal["days", "weeks", "months"]
    deadline_before: Literal["signing", "renewal", "next-audit"] | None

class RemediationPlan(BaseModel):
    items: list[RemediationItem]
    summary: str                          # 2-3 sentence executive summary
```

### 5.3 ESG Agent

**File:** `src/orchestra_tprm/agents/specialists/esg.py`

**Purpose:** Sixth specialist — reviews vendor's ESG disclosures against policy.

**Position in graph:** Parallel with the other 5 specialists.

**Input:** Documents tagged `esg` by `DocRouterAgent` (sustainability report, governance disclosures, supplier code of conduct, diversity report).

**Dependency:** `DocRouterAgent` does not currently emit the `esg` tag. We extend its prompt and routing table to recognize ESG document types (sustainability report, code of conduct, diversity report, governance disclosure). Tracked as part of work item B.

**Process:** Same pattern as `LegalAgent` and `SecurityAgent` — LLM extracts findings against a checklist:
- **Environmental:** Carbon commitments (Net Zero year, Scope 1/2/3 disclosure), energy mix, e-waste policy
- **Social:** DEI metrics, supply-chain labour audits, modern slavery statement, customer privacy
- **Governance:** Board independence, audit committee, anti-corruption policy, whistleblower protection

**Output:** `list[Finding]` (same schema as other specialists).

**Policy additions:** Both `vendor.yaml` and `ma.yaml` get new `critical_categories` entries (`net-zero-commitment`, `modern-slavery-statement`, `anti-corruption-policy`).

## 6. Demo Flow (judges' journey)

1. Judge opens `https://orchestra-tprm.run.app` → sees TPRM landing page
2. Picks **HashiCorp** from example chooser (or uploads their own packet)
3. Selects **Vendor Onboarding** mode (default)
4. Clicks **Run Review** → POST to `/api/v1/runs`, returns `run_id`
5. Page navigates to `/tprm/runs/:runId` → React opens SSE stream
6. Live updates flow in: intake → doc_router → active specialists firing in parallel (5 for vendor mode: Legal, Security, Code, External, ESG; 6 for M&A mode: adds Financial). NodeCard chips light up as each completes
7. Findings populate the table as they come in (severity colour-coded)
8. Risk score card animates from 0 to final value when `risk_score` node completes
9. Policy verdict appears (green/amber/red banner)
10. Remediation roadmap renders below findings
11. Coordinator completes → Google Sheet link appears with a "View" button
12. Judge clicks the Sheet link → opens populated Sheet in new tab → can see all findings written live

End-to-end: ~45–60 seconds. Total Gemini cost per demo: ~$0.05.

## 7. Submission Deliverables

### 7.1 Form fields

| Field | Value (draft) |
|---|---|
| Title | **Orchestra TPRM — Multi-Agent Vendor Risk Review** |
| Short description (≤255 chars) | Production-grade multi-agent framework + a TPRM application that replaces $50K/year tools. Six Gemini-powered specialists score vendors in 60s. Built on Orchestra, deployed on Cloud Run. |
| Long description (≥100 words) | See §7.2 below |
| Technology tags | `gemini`, `google-ai-studio`, `python`, `fastapi`, `react`, `cloud-run`, `bigquery`, `multi-agent`, `langgraph-alternative` |
| Category tags | `enterprise`, `risk-management`, `compliance`, `agents` |
| Cover image | 16:9 hero showing risk dashboard with HashiCorp scorecard. PNG. |

### 7.2 Long description (draft, to be refined)

Third-party risk management is a $5B enterprise category dominated by OneTrust, ProcessUnity, and Vanta — tools that charge $50K-$500K per year for what is fundamentally a document-review workflow.

Orchestra TPRM replaces them with a six-specialist agent system powered by Google Gemini 2.5 Flash. Upload a vendor packet (MSA, SOC 2 report, security questionnaire, financial statements, ESG disclosures, GitHub URL) and six specialists run in parallel — Legal, Security, Code, External, Financial, ESG — extracting structured findings against a configurable policy pack. A Risk Scoring agent rolls findings into a single 0–100 score, a Policy agent issues an approve / conditional / reject verdict, and a Remediation agent generates a prioritized action plan with specific contractual leverage points.

The system runs both vendor onboarding mode and M&A due diligence mode. Outputs land in Google Sheets and Docs that procurement, legal, and deal teams already use.

It is built on Orchestra, a Python multi-agent framework with first-class support for the Google AI Studio API, BigQuery, Cloud Run, and the rest of the GCP stack — and it ships today on a public Cloud Run deployment with a live React dashboard streaming events over SSE.

### 7.3 Slide deck outline (10 slides, ~3 min spoken)

1. **Cover** — Orchestra TPRM logo, hackathon, team, date
2. **The problem** — TPRM tools cost $50K-$500K/year, take weeks per vendor, brittle workflows
3. **The solution** — multi-agent review in 60s on Gemini Flash
4. **Live demo** — annotated screenshot of dashboard with risk score, findings, remediation
5. **Architecture** — Orchestra graph + 6 specialists + GCP integration diagram
6. **Why Orchestra** — 4 differentiators vs LangGraph/CrewAI (typed state, scripted testing, cost-aware routing, GCP-native)
7. **Market & TAM** — $5B TPRM, $14B GRC, growing 12% CAGR
8. **Revenue model** — open-source framework, SaaS for TPRM tier ($5K-$50K/year per buyer)
9. **Roadmap** — sanctions screening, vendor onboarding API, ServiceNow integration
10. **CTA** — GitHub link, demo URL, contact

### 7.4 Video script outline (5 min)

| Time | Content |
|---|---|
| 0:00–0:30 | Hook: "TPRM costs enterprises $5B a year. Watch six AI agents do it in 60 seconds." |
| 0:30–1:00 | Problem framing + business cost |
| 1:00–3:30 | Live demo walkthrough — upload, dashboard, findings appear in real-time, risk score, remediation, Sheet output |
| 3:30–4:15 | Architecture: Orchestra graph, Gemini integration, Cloud Run |
| 4:15–4:45 | Differentiators + market |
| 4:45–5:00 | CTA — GitHub, demo URL |

## 8. Coordination With Other Instance

| File area | Owner | Notes |
|---|---|---|
| `src/orchestra_tprm/server/app.py` | Other instance (#11) | Do NOT edit here |
| `src/orchestra_tprm/server/sse.py` (new) | Other instance (#11) | |
| `src/orchestra_tprm/agents/specialists/*.py` (existing 5) | Either — read-only here unless bug fix | |
| `src/orchestra_tprm/agents/risk_score.py` (new) | **This instance** | |
| `src/orchestra_tprm/agents/remediation.py` (new) | **This instance** | |
| `src/orchestra_tprm/agents/specialists/esg.py` (new) | **This instance** | |
| `src/orchestra_tprm/graph.py` | Shared — coordinate via PR / sync | Both instances will add nodes |
| `src/orchestra_tprm/schemas.py` | Shared — coordinate | CR-02 bug fix + RiskScore + RemediationPlan |
| `src/orchestra_tprm/agents/base.py` | Other instance — bug fix CR-01 (strip_json_fences) | |
| `src/orchestra_tprm/cli.py` | Other instance — CR-05 (replay fallback) | |
| `src/orchestra_tprm/agents/coordinator.py` | Other instance — CR-04 (fence strip in coordinator) | |
| `src/orchestra/ui/src/pages/TprmLanding.tsx` (new) | **This instance** | |
| `src/orchestra/ui/src/pages/TprmRunDetail.tsx` (new) | **This instance** | |
| `Dockerfile` | Coordinate — both need Cloud Run config | |
| `cloudbuild.yaml` (new) | **This instance** | |
| `deploy/cloud-run/service.yaml` (new) | **This instance** | |

Sync mechanism: this design doc is the canonical spec. Other instance reviews it before starting overlapping work. We commit to `main` frequently; rebase often.

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Gemini rate-limit during heavy judging traffic | Medium | High | Cache last successful HashiCorp run as replay fallback; serve from `--replay` when `429` returned |
| FastAPI wiring (#11) slips | Medium | Critical | This instance starts agent work in parallel; agents are pure Python and don't depend on server |
| BigQuery / Sheets IAM blocks Cloud Run | Medium | High | Provision SA + roles on Day 1, test write before agent work; fall back to mocked writes for demo |
| Two instances stomp on `graph.py` | High | Medium | Strict coordination via this doc; new nodes added via append; merge by hand if needed |
| Video recording bugs / OBS crash | Low | High | Record draft on Day 2; final on Day 3 morning |
| Cloud Run cold start hurts first-impression | Low | Medium | Set `min-instances=1` for judging window (cost: ~$3/day, worth it) |
| Demo run takes > 90s and judges close tab | Low | Medium | Risk score appears at ~30s mark from specialist join; full run by 60s |
| New agent prompt regresses existing findings count | Medium | Medium | Snapshot HashiCorp output before changes; assert ≥ 30 findings post-change |

## 10. Timeline

### Day 1 — Friday 2026-05-16 (today, partial)

- **Morning (this instance):** This design doc, fix bug CR-02 (severity normalization — blocks all specialists)
- **Afternoon (this instance):** Build Risk Scoring Agent + Remediation Agent + ESG Agent (all 3)
- **Parallel (other instance):** FastAPI wiring (#11), bug fixes CR-01, CR-03, CR-04, CR-05
- **End of day:** All 3 new agents have unit tests passing, FastAPI returns real run state

### Day 2 — Saturday 2026-05-17

- **Morning (this instance):** TPRM-specific React pages, wire to existing useSSE hook
- **Afternoon (this instance):** Cloud Run deployment, GCP service account, IAM, end-to-end test with real Gemini calls
- **Parallel (other instance):** Replay mode (#12), CI workflow, replay capture from successful run
- **End of day:** Public Cloud Run URL works; full HashiCorp demo runs end-to-end

### Day 3 — Sunday 2026-05-18

- **Morning:** Slide deck (PDF), cover image
- **Afternoon:** Video recording (live demo + voiceover), edit, export MP4
- **Evening:** Submission form fill on lablab.ai, double-check everything
- **Buffer:** Bug fixes, replay fallback testing, sleep

### Deadline — Monday 2026-05-19 08:00 SGT

Submit by 06:00 SGT (2hr buffer). Repo public, demo URL live, video + slides uploaded.

## 11. Success Criteria

The submission is successful if:

1. lablab.ai form is submitted before deadline with all 8 required fields populated
2. GitHub repo is public and contains all source code (Orchestra + TPRM)
3. Cloud Run demo URL is reachable and runs a HashiCorp review end-to-end in < 90s
4. Video is < 5 min, MP4 format, walks through problem → solution → demo → architecture
5. Slide deck is PDF, ≤ 12 slides, covers all judging criteria
6. Demo shows the 3 new agents (Risk Scoring score, Remediation roadmap, ESG findings) — these are our originality differentiators
7. Live Gemini calls work during the demo (judges see real-time agent execution via SSE)

Judging window starts within 7 days of deadline. The Cloud Run deployment must remain stable and Gemini quota must remain available until at least 2026-05-26.

---

**End of design.** Awaiting user review before invoking `writing-plans` skill.
