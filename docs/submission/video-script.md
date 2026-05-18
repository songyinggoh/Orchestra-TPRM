# 5-minute demo video script

Total target: 4:30–4:50 (leave buffer for cuts). 14 slides + 3 live screens.

## Scene 1 — Cover (0:00–0:15)

> **Voiceover:** "Orchestra is a Python multi-agent framework, and Orchestra Third-Party Risk Review is an enterprise application built on it. Today I'll show you both layers, end to end, in under five minutes, running live on Google Cloud Run with Gemini 2.5 Flash."

Visual: slide 1 (cover).

## Scene 2 — Problem (0:15–0:35)

> "Third-party risk review is slow, expensive, and document-heavy. A typical vendor onboarding takes 3–6 weeks and $15-50K per review. M&A due diligence runs 6–12 weeks at $200K to $2M per target. Existing GRC platforms are designed for compliance officers — not for the deal-time question, *should we proceed?*"

Visual: slide 2 (problem).

## Scene 3 — Solution (0:35–0:55)

> "Orchestra compresses that work into under 90 seconds. A multi-agent pipeline reviews the packet in parallel, produces a scored verdict, a prioritized remediation plan with contract leverage, and writes a Google Sheet or Doc deal memo. All powered by Gemini 2.5 Flash."

Visual: slide 3 (solution).

## Scene 4 — Architecture (0:55–1:25)

> "Here's the pipeline. Intake materializes documents. Router classifies them. Seven specialists run in parallel — legal, security, code, external, financial, ESG, and a SaaS-metrics specialist for M&A. They join into a deterministic Risk Score, then a Policy agent applies the rule pack, then a Remediation agent produces the action plan, then the Coordinator writes the output. M&A mode adds a 100-day post-close planner at the end."

Visual: slide 4 (architecture graph).

## Scene 5 — Live demo, landing page (1:25–1:45)

> "Let's run it live. This is the dashboard, served from a single Cloud Run service. Two example packets are pre-loaded: HashiCorp for M&A, Acme Cloud Analytics for vendor onboarding."

Visual: live screen — landing page with two tiles.

## Scene 6 — Live demo, mid-run (1:45–2:30)

> "I'll click HashiCorp. The pipeline starts streaming Server-Sent Events. Each NodeCard transitions from pending to running to done as the specialist returns. Watch the findings table populate in real time — legal flags a change-of-control clause, security flags a SOC 2 gap, code flags the BSL license transition, financial flags the negative operating margin, ESG flags a missing modern-slavery statement."

Visual: live run, NodeCards lighting up.

## Scene 7 — Risk score + remediation (2:30–3:15)

> "After all specialists join, the Risk Score agent produces a 0-to-100 verdict — 73 out of 100, **red**. Three top risk drivers are explained inline. The Remediation Roadmap groups action items by priority: P0, P1, P2. Each card shows the buyer-side leverage — for HashiCorp, that's SPA reps and warranties with 18-month survival, or rep-and-warranty insurance, or escrow against the BSL fragmentation risk. Click any card to see the linked finding."

Visual: live screen — RiskScoreHero + RemediationRoadmap.

## Scene 8 — Sheet / Doc output (3:15–3:45)

> "The Coordinator writes the full memo to a Google Doc. Executive Summary, **Risk Score** section, IC Memo with proceed/reprice/walk recommendation, Workstream Reports per workstream, Risk Register, **Remediation Roadmap**, PMI 100-day plan, and a machine-readable appendix. For vendor mode, it writes one row to a Google Sheet with the same columns plus a CSV mirror."

Visual: live screen — Google Doc output.

## Scene 9 — Why Orchestra (3:45–4:15)

> "Compared to LangGraph and CrewAI: Orchestra is the only one with typed state and merge reducers, compile-time graph validation, a scripted-LLM test harness with 300+ unit tests, a cost-aware router, and a single Cloud-Run-native binary. The replay JSONL means demos and CI runs are deterministic — no Gemini quota burned for every PR."

Visual: slide 13 (Why Orchestra comparison table).

## Scene 10 — Market + close (4:15–4:50)

> "Open-source framework, SaaS for the application, enterprise tier on top. Roadmap covers sanctions, privacy, ServiceNow, Jira, Workday. Repo on GitHub, live demo URL on screen. Thanks for watching."

Visual: slide 14 (Roadmap + CTA) → cover.

---

## Recording checklist

- [ ] Set browser to 1920×1080, full screen
- [ ] Use Chrome incognito (no extensions in screen)
- [ ] OBS Studio, 1080p60, MP4
- [ ] Mic test: levels around -12dB to -6dB
- [ ] Pre-warm Cloud Run (one cold-start eats 3-5s) — hit /health first
- [ ] Pre-stage HashiCorp run so SSE starts the moment the click lands
- [ ] One full take, then edit cuts if needed
- [ ] Export H.264 MP4, target <100 MB
