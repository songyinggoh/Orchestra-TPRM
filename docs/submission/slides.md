<!-- Marp slide deck — convert with `npx @marp-team/marp-cli docs/submission/slides.md -o docs/submission/slides.pdf` -->
---
marp: true
theme: default
size: 16:9
paginate: true
backgroundColor: "#0f1115"
color: "#e6e9ef"
style: |
  section {
    font-family: 'Roboto', sans-serif;
    padding: 60px;
  }
  h1 {
    color: #e6e9ef;
    border-bottom: 2px solid #1f2329;
    padding-bottom: 12px;
  }
  h2 {
    color: #c4cad4;
  }
  strong {
    color: #fbbf24;
  }
  code {
    background: #15181e;
    color: #86efac;
    padding: 2px 6px;
    border-radius: 3px;
  }
  blockquote {
    border-left: 3px solid #fbbf24;
    padding-left: 16px;
    color: #c4cad4;
    font-style: italic;
  }
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th, td {
    padding: 8px 12px;
    border-bottom: 1px solid #1f2329;
    text-align: left;
  }
  .verdict-red { color: #f87171; font-weight: 600; }
  .verdict-amber { color: #fbbf24; font-weight: 600; }
  .verdict-green { color: #86efac; font-weight: 600; }
---

<!-- _class: cover -->

# Orchestra

## Multi-Agent Third-Party Risk Review on Google Gemini

**Hackathon submission** — lablab.ai *Transforming Enterprise Through AI*, Track 2 (Google AI Studio)

2026-05-19

---

# The problem

Third-party risk review is **slow, expensive, and document-heavy**.

- Vendor onboarding: 3–6 weeks per vendor, $15-50k per review, manual SOC 2 / MSA / financial / source-code workstreams
- M&A due diligence: 6–12 weeks, $200k–$2M per target, same workstreams plus PMI planning
- Existing tools (GRC platforms): designed for compliance officers, not for **deal-time decisions**

**Judges' problem:** procurement and corp-dev teams burn 40–60 hours per packet on first-pass review *before* anyone can say "should we even proceed?"

---

# The solution

A multi-agent pipeline that produces, in **under 90 seconds**:

1. A scored verdict (0–100 risk score, traffic-light)
2. A prioritized **remediation plan** (P0/P1/P2 actions with contract leverage)
3. A Google Sheet (vendor) or **Doc deal memo** (M&A)

Built on **Orchestra**, a Python multi-agent framework with typed state, compile-time graph validation, and scripted-LLM testing.

---

# Architecture

```
bootstrap → intake → router
                ↓
   ┌────────────────────────────────┐
   │   7 specialists in parallel    │
   │   legal · security · code      │
   │   external · financial · esg   │
   │   saas_metrics (M&A only)      │
   └────────────────────────────────┘
                ↓ join
            risk_score    ← deterministic math + LLM rationale (NEW)
                ↓
              policy      ← weighted score + ICMemo (M&A)
                ↓
           remediation    ← mode-aware action plan (NEW)
                ↓
           coordinator    ← Sheet (vendor) or Doc (M&A)
                ↓
          pmi_planner     ← 100-day plan (M&A only)
                ↓
               END
```

Single Cloud Run service · BigQuery audit trail · SSE-streamed dashboard

---

# The agent pipeline

| Stage | Agent | Output |
|---|---|---|
| Intake | `intake_node` | resolves packet manifest, materializes URIs |
| Routing | `DocRouterAgent` | LLM-driven document → specialist assignment |
| Specialists (parallel) | `Legal`, `Security`, `Code`, `External`, `Financial`, `SaaSMetrics`, `ESG` | per-domain `Finding[]` |
| Risk Score | `RiskScoreAgent` | 0–100 score + traffic-light + top 3 drivers |
| Policy | `PolicyAgent` | YAML-driven verdict + `ICMemo` (M&A) |
| Remediation | `RemediationAgent` | P0/P1/P2 action plan with contract leverage |
| Coordinator | `Coordinator` | Sheet row (vendor) or Doc sections (M&A) |
| PMI Planner | `PMIPlannerAgent` | 100-day post-close plan (M&A only) |

---

# Live demo — landing page

**[Screenshot 1 placeholder — landing page with HashiCorp + Acme tiles]**

Two example packets pre-loaded:

- **HashiCorp** (M&A): 10-K + acquisition agreement + codebase audit — *55 findings, reject verdict, risk score 700/1000*
- **Acme Cloud Analytics** (vendor): MSA + SOC 2 — *27 findings, conditional approve, risk score 171/1000*

Both runs are recorded into `examples/tprm/*/replay.jsonl` for offline replay.

---

# Live demo — mid-run

**[Screenshot 2 placeholder — NodeCards lighting up as specialists complete]**

- Server-Sent Events push every `node_started` / `node_completed` event
- Dashboard renders a NodeCard per agent that transitions `pending → running → done`
- Findings table populates in real time as each specialist returns
- Median end-to-end: **~78s** (Gemini 2.5 Flash, 7-way parallel fan-out)

---

# Live demo — risk score + remediation

**[Screenshot 3 placeholder — RiskScoreHero + RemediationRoadmap]**

- **RiskScoreHero**: 0-100 numeric, verdict pill (<span class="verdict-amber">AMBER</span>), per-dimension bars
- **RemediationRoadmap**: P0/P1/P2 Kanban; click each card to see the linked Finding + contract leverage

Both fields are produced live by the new `RiskScoreAgent` + `RemediationAgent` and streamed via SSE to the React UI.

---

# Live demo — Google Sheet output

**[Screenshot 4 placeholder — Sheets with row appended]**

Vendor mode writes a row to a Google Sheet:

| subject | verdict | risk_score | risk_assessment | remediation | categories |
|---|---|---|---|---|---|
| Acme | conditional-approve | 171 | 42/100 (amber) | 3 items, 30d | liability,soc2,esg... |

M&A mode writes a full deal memo to a Google Doc with sections: Executive Summary, **Risk Score**, IC Memo, Workstream Reports, Risk Register, **Remediation Roadmap**, PMI 100-Day Plan, Appendix.

---

# Spotlight: Risk Scoring Agent

**Position:** after specialists join, before policy.

**Hybrid math + LLM:**

- Deterministic Python computes `overall = round(100 · Σ weights[severity] / max_possible)`
- LLM (Gemini 2.5 Flash) generates only the **explanation** + 3 driver one-liners
- **Fail-soft:** if Gemini errors, template strings fill in — demo never crashes

**Verdict thresholds (configurable per mode):**

| Mode | Green | Amber | Red |
|---|---|---|---|
| Vendor | 0–30 | 31–69 | 70–100 |
| M&A | 0–20 | 21–59 | 60–100 |

---

# Spotlight: Remediation Agent

**Position:** after policy. **Skipped** when verdict ∈ {approve, proceed} AND no ≥medium findings.

**Mode-aware prompts:**

- **Vendor**: "For each finding, write the action the **vendor** must take before signing. Leverage = contract clause / certification."
- **M&A**: "For each finding, write the action the **buyer** can take via deal terms: price reduction, indemnity, escrow, RWI, post-close monitoring. Leverage = SPA clause / RWI policy."

Output: `RemediationPlan(items: list[RemediationItem], horizon_days: int, summary: str)` — rendered as P0/P1/P2 Kanban in the dashboard.

---

# Spotlight: ESG Agent

**Why ESG matters in 2026:** EU CSRD, UK MSA 2015, US SEC climate disclosure rules all in force.

**13 controlled categories** across three pillars:

- **Environmental:** net-zero commitment, Scope 1/2/3 emissions, renewable energy mix, e-waste policy
- **Social:** DEI metrics, supply-chain labour audit, modern slavery statement, customer privacy framework
- **Governance:** board independence, audit committee, anti-corruption policy, whistleblower protection, security audit cadence

Default-active in **both vendor and M&A modes**. `critical_categories` in policy YAML flag any missing **net-zero**, **modern slavery**, or **anti-corruption** statement.

---

# Why Orchestra

**Compared to LangGraph / CrewAI:**

| | Orchestra | LangGraph | CrewAI |
|---|---|---|---|
| Typed state with merge reducers | ✓ | partial | ✗ |
| Compile-time graph validation | ✓ | ✗ | ✗ |
| Scripted-LLM test harness | ✓ | ✗ | ✗ |
| Cost-aware router (Thompson sampling) | ✓ | ✗ | ✗ |
| Cloud-Run-native single binary | ✓ | ✗ | ✗ |
| Replay JSONL for deterministic demos | ✓ | ✗ | ✗ |
| Native Google AI Studio integration | ✓ | partial | partial |

300+ unit tests · 7 LLM provider backends · Apache-2.0

---

# Market & business model

**TAM:** $34B GRC software (Gartner 2025) + $18B due-diligence services market

**SAM:** mid-market procurement + corp-dev teams (5k-50k employee orgs) → $4B

**Model:**

1. **Open-source framework** (Orchestra) — adoption flywheel, GitHub stars, ecosystem
2. **SaaS for the TPRM application** — $50k/year per team, includes BigQuery + Drive provisioning, custom policy packs, integrations
3. **Enterprise** — on-prem Helm chart, custom specialists, SLA

---

# Roadmap + CTA

**Next 90 days:**

- Sanctions screening agent (OFAC, EU, UK lists)
- Privacy agent (GDPR Art. 30 + DPIA generator)
- ServiceNow + Jira integrations
- Workday vendor master ingestion

**Try it now:**

- **Live demo:** https://orchestra-tprm-67479435861.us-central1.run.app
- **Repo:** https://github.com/songyinggoh/Orchestra
- **Replay** the HashiCorp run offline with `python -m orchestra_tprm --mode ma --packet examples/tprm/hashicorp --replay examples/tprm/hashicorp/replay.jsonl`

**Track 2 — Google AI Studio / Gemini 2.5 Flash**
