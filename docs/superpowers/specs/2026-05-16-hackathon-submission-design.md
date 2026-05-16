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

Judges score on Presentation, Business Value, Application of Technology, and Originality. Our strategy is to demonstrate that Orchestra makes enterprise-grade multi-agent applications fast to build, and that the TPRM application is a working example of that — not a slideware concept.

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
                        │       SA: orchestra-tprm-runner   │
                        │                                   │
   judges browser ─────►│  FastAPI (orchestra-tprm)         │
                        │   ├── /api/v1/runs        (POST)  │
                        │   ├── /api/v1/runs/.../stream     │
                        │   ├── /api/v1/tprm/scorecard      │
                        │   ├── /api/v1/tprm/upload (POST)  │
                        │   └── /  (static React build)     │
                        │                                   │
                        └──────────────────────────────────┘
                                       │
                ┌──────────┬───────────┼────────────┬─────────────┐
                ▼          ▼           ▼            ▼             ▼
        generativelanguage  bigquery   sheets/docs   gcs       (no auth wall)
        .googleapis.com     .google    .googleapis   bucket    open access
        Gemini 2.5 Flash    BQ writes  link-share    uploads   (rate-limited
        AI Studio — free    via SA     write via SA  via SA     by Cloud Run)
```

**Decisions:**
- **Public access:** open URL, no auth wall. Cloud Run concurrency limits + Gemini rate-limits act as soft throttle.
- **Cloud Run service account:** dedicated `orchestra-tprm-runner@<project>.iam.gserviceaccount.com` (not default compute SA).
- **GCP API auth from Cloud Run:** Application Default Credentials picks up the service account automatically. No JSON key in Secret Manager.
- **`GOOGLE_API_KEY` (AI Studio):** stored as a Cloud Run secret, mounted as an env var. Distinct from the SA — AI Studio billing is separate.
- **Sheet sharing:** every Sheet/Doc created by the Coordinator has link-sharing enabled (view-only, anyone-with-link). URL returned in the run completion event.
- **Vendor packet uploads:** `POST /api/v1/tprm/upload` writes the file to `gs://orchestra-tprm-uploads-<project-hash>/{run_id}/{filename}` via the runner SA. Packets persist across instance restarts.
- **Run/event persistence:** BigQuery dataset `orchestra_tprm` with tables `runs` (one row per run, status + metadata) and `events` (one row per SSE event, sequence-ordered, append-only). Streaming inserts via the runner SA. Live state during a run comes from in-process memory streamed over SSE; BigQuery is the after-the-fact record so judges can re-open a previous run via `GET /api/v1/runs/{run_id}` which reads from BQ. Read pattern is `SELECT * FROM events WHERE run_id = ? ORDER BY sequence` — sub-500ms even cold. Free tier covers all demo traffic (streaming insert cost ~$0.00001/run).

- Single Cloud Run service serves FastAPI + static React build
- Gemini API via `GOOGLE_API_KEY` (Cloud Run secret) — AI Studio billing, free tier, no GCP credits consumed
- BigQuery + Sheets + Docs via Cloud Run service account with IAM roles
- **`min-instances=1` for the 7-day judging window** to eliminate cold start; revert to scale-to-zero after 2026-05-26 (cost during window: ~$3-5/day)

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

**Schema prerequisite:** The `Finding` model in `src/orchestra_tprm/schemas.py` gains a stable `id: str` field generated as a UUID4 at construction (`Field(default_factory=lambda: uuid.uuid4().hex)`). All 5 existing specialists already construct `Finding(...)` via `safe_specialist`; no per-specialist change is needed because the default factory fires automatically. The `RemediationItem.finding_id` field references this stable ID, enabling the React UI to render a Findings ↔ Remediation join.

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

The landing page exposes **both** examples (HashiCorp vendor onboarding, Acme M&A due diligence) so judges can run either. The video, slide deck, and cover image all use the HashiCorp vendor path because it is the most validated (33 findings already produced in a green E2E run) and lowest-risk to reproduce live.

1. Judge opens `https://orchestra-tprm.run.app` → sees TPRM landing page with two example tiles (HashiCorp vendor / Acme M&A) and a custom upload option
2. Picks **HashiCorp** tile (pre-selected by default) — or clicks the Acme M&A tile to see the alternate flow
3. Mode is auto-set by the chosen tile (vendor for HashiCorp, M&A for Acme)
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
| Title | **Orchestra — Multi-Agent Third-Party Risk Review on Google Gemini** |
| Short description (≤255 chars) | A Python multi-agent framework and an enterprise risk-review application built on it. Six Gemini 2.5 Flash specialists review vendor packets in parallel and produce a scored verdict, remediation plan, and Google Sheet report on Cloud Run. |
| Long description (≥100 words) | See §7.2 below |
| Technology tags | `gemini`, `google-ai-studio`, `python`, `fastapi`, `react`, `cloud-run`, `bigquery`, `multi-agent`, `langgraph-alternative` |
| Category tags | `enterprise`, `risk-management`, `compliance`, `agents` |
| Cover image | 16:9 PNG, split panel: left half is the live React dashboard (HashiCorp run mid-execution, risk score + colour-coded findings), right half is the agent graph diagram (6 specialists fanning out to risk_score → policy → remediation → coordinator). Orchestra wordmark top-left, "On Google Gemini" line bottom-right. |

### 7.2 Long description (measured / technical tone)

Orchestra is a Python multi-agent orchestration framework for production deployment on Google Cloud. It provides typed state with reducer functions for concurrent updates, compile-time graph validation, a scripted-LLM testing harness, and native support for the Google AI Studio API alongside six other LLM backends.

Orchestra Third-Party Risk Review is an enterprise application built on the framework. It processes vendor documentation — master service agreements, SOC 2 reports, security questionnaires, financial statements, ESG disclosures, and source repositories — through a six-specialist agent pipeline powered by Gemini 2.5 Flash. Each specialist extracts structured findings against a configurable policy pack: Legal reviews contract clauses, Security checks SOC 2 control coverage, Code analyzes source repositories for risk, External assesses news and reputation signals, Financial evaluates business continuity indicators, and ESG measures environmental, social, and governance disclosures.

After the specialists join, a Risk Scoring agent aggregates findings into a 0–100 score with a traffic-light verdict, a Policy agent evaluates the verdict against the active policy pack, and a Remediation agent generates a prioritized action plan with specific contractual leverage points. A Coordinator writes the final report to a Google Sheet (vendor onboarding mode) or a Google Doc (M&A due diligence mode).

The system runs on a single Cloud Run service serving a FastAPI backend and a React dashboard. The dashboard streams agent execution events over Server-Sent Events, allowing reviewers to watch the multi-agent pipeline complete in real time. BigQuery stores findings for cross-vendor analytics. The deployment uses the Google AI Studio free tier for inference and does not consume GCP credits.

### 7.3 Slide deck outline (15 slides, ~4 min spoken)

The deck doubles as a standalone artifact judges can read after the video. Each slide carries 2-3 sentences plus one visual.

1. **Cover** — title, Orchestra wordmark, hackathon name, team, date
2. **The problem** — third-party risk review is slow, expensive, and document-heavy; existing tools are GRC platforms with long workflows
3. **The solution** — multi-agent review that produces a scored verdict, action plan, and Sheet report in under 90 seconds
4. **Architecture overview** — Orchestra graph + 6 specialists + GCP integration diagram
5. **The agent pipeline** — visual of intake → router → 6 specialists → risk score → policy → remediation → coordinator
6. **Demo screenshot 1** — landing page with HashiCorp and Acme example tiles
7. **Demo screenshot 2** — live React dashboard mid-run, NodeCards lighting up as specialists complete
8. **Demo screenshot 3** — risk score hero + findings table + remediation roadmap
9. **Demo screenshot 4** — Google Sheet output, populated live by the Coordinator
10. **Spotlight: Risk Scoring agent** — how the 0-100 score and traffic-light verdict are computed
11. **Spotlight: Remediation agent** — example output with prioritised, mode-aware action items
12. **Spotlight: ESG agent** — what it covers and why it differentiates from existing tools
13. **Why Orchestra** — typed state, scripted-LLM testing, cost-aware routing, GCP-native; comparison to LangGraph / CrewAI
14. **Market & business model** — TAM, SAM, open-source framework + SaaS tier for the application
15. **Roadmap + CTA** — next agents (sanctions, privacy), integrations (ServiceNow, Jira), GitHub link, demo URL

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

### 8.1 Replay capture

**Format:** JSONL of LLM call recordings (input prompt + output text) consumed by Orchestra's existing `ReplayProvider`. The graph re-executes from scratch on each replay run; only the Gemini calls are served from disk. Agent-code changes still take effect on replay runs without requiring re-capture — only prompt changes invalidate the recording.

**Files (committed to repo):**
- `examples/tprm/hashicorp/replay.jsonl`
- `examples/tprm/acme/replay.jsonl`

**Capture command:** existing TPRM CLI with a `--capture <path>` flag (added in this work) wraps `GoogleProvider` with a tee that writes every LLM call to JSONL while passing the response through.

**Capture timing:**
- Day 2 evening: first capture after all 3 new agents land and prompts stabilize
- Day 3 morning: re-capture if any prompt changed; final captures committed before video recording

**Read path:** FastAPI's run launcher attempts live Gemini first. On `RateLimitError` (429), `ProviderUnavailableError` (5xx), or any agent-level exception escaping `safe_specialist`, it re-launches the same graph through `ReplayProvider.from_jsonl(...)` and tags the run state with `serving_mode = "replay"`. The React UI reads `serving_mode` from the run state and renders a small badge.

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Gemini rate-limit during heavy judging traffic | Medium | High | Hybrid live-with-replay-fallback. Every run launches against live Gemini by default; FastAPI handler catches `429` (and other transient errors) and re-launches the same graph through `ReplayProvider` against the committed JSONL recording. Small "live" / "from cache" badge in the UI reflects which path served the run. |
| Acme M&A coordinator bug (CR-04) not fixed by Day 2 | Medium | Medium | Same hybrid fallback covers this — Acme tile always works because the replay path is bug-independent (replay JSONL captured against a known-good prompt). When CR-04 lands, live runs work too. |
| FastAPI wiring (#11) slips | Medium | Critical | This instance starts agent work in parallel; agents are pure Python and don't depend on server |
| BigQuery / Sheets IAM blocks Cloud Run | Medium | High | Provision SA + roles on Day 1, test write before agent work; fall back to mocked writes for demo |
| Two instances stomp on `graph.py` | High | Medium | Strict coordination via this doc; new nodes added via append; merge by hand if needed |
| Video recording bugs / OBS crash | Low | High | Record draft on Day 2; final on Day 3 morning |
| Cloud Run cold start hurts first-impression | Resolved | — | **Set `min-instances=1` for the judging window** (~$3-5/day, decided). Revert to scale-to-zero after the 7-day judging window closes (~2026-05-26). |
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
