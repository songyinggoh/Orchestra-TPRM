# lablab.ai submission form — copy/paste content

## Title (≤ 80 chars)

```
Orchestra — Multi-Agent Third-Party Risk Review on Google Gemini
```

## Short description (≤ 255 chars)

```
A Python multi-agent framework and an enterprise risk-review application built on it. Seven Gemini 2.5 Flash specialists review vendor/M&A packets in parallel and produce a scored verdict, remediation plan, and Google Sheet or Doc deal memo on Cloud Run.
```

## Long description (≥ 100 words, ~2200 chars)

```
Orchestra is a Python multi-agent orchestration framework for production deployment on Google Cloud. It provides typed state with reducer functions for concurrent updates, compile-time graph validation, a scripted-LLM testing harness, and native support for the Google AI Studio API alongside six other LLM backends.

Orchestra Third-Party Risk Review is an enterprise application built on the framework. It processes vendor documentation — master service agreements, SOC 2 reports, security questionnaires, financial statements, ESG disclosures, and source repositories — through a seven-specialist agent pipeline powered by Gemini 2.5 Flash. Each specialist extracts structured findings against a configurable policy pack: Legal reviews contract clauses, Security checks SOC 2 control coverage, Code analyzes source repositories for risk, External assesses news and reputation signals, Financial evaluates business continuity indicators, ESG measures environmental/social/governance disclosures (net-zero commitment, modern slavery statement, anti-corruption policy), and SaaSMetrics (M&A mode only) extracts ARR, NRR, GRR, CAC payback, and Rule-of-40 against deal-stopper thresholds.

After the specialists join, a Risk Scoring agent aggregates findings into a 0-100 score with a traffic-light verdict and three explained risk drivers. A Policy agent evaluates the verdict against the active policy pack and produces an Investment Committee memo (M&A mode). A Remediation agent generates a prioritized P0/P1/P2 action plan with specific contractual leverage points — vendor mode frames each action as "vendor must do X before signing"; M&A mode frames it as "buyer negotiates X via SPA reps, indemnity, escrow, or RWI." A Coordinator writes the final report to a Google Sheet (vendor onboarding mode) or a Google Doc deal memo (M&A due diligence mode).

The system runs on a single Cloud Run service serving a FastAPI backend and a React dashboard. The dashboard streams agent execution events over Server-Sent Events, letting reviewers watch the multi-agent pipeline complete in real time with NodeCards that transition pending → running → done as each specialist returns. BigQuery stores findings for cross-vendor analytics. The deployment uses the Google AI Studio free tier for Gemini 2.5 Flash inference and does not consume GCP credits.
```

## Technology tags

```
gemini, google-ai-studio, python, fastapi, react, cloud-run, bigquery, multi-agent, langgraph-alternative, sse
```

## Category tags

```
enterprise, risk-management, compliance, agents, due-diligence
```

## Cover image

Path: `docs/submission/cover.png` (16:9, 1920×1080)

## Slide deck

Path: `docs/submission/slides.pdf` (Marp-exported PDF, 14 slides)

## Demo video

Path: `docs/submission/demo.mp4` (≤ 5 min, MP4)

## Demo URL

```
https://orchestra-tprm-67479435861.us-central1.run.app
```

## GitHub repo

```
https://github.com/songyinggoh/Orchestra
```

## Track

```
Track 2 — AI Agents with Google AI Studio
```
