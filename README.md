# Orchestra — Multi-Agent Third-Party Risk Review on Google Gemini

A multi-agent framework and TPRM application that compresses a 4-week vendor or M&A due-diligence review into ~60 seconds of parallel agent work, powered by Google Gemini 2.5 Flash.

> **Hackathon submission** — [lablab.ai *Transforming Enterprise Through AI*](https://lablab.ai/), Track 2 (AI Agents with Google AI Studio). Submitted 2026-05-19.

---

## What it does

Feed in a vendor packet (SOC 2, MSA, GitHub repo) or an M&A packet (10-K, acquisition agreement, codebase audit). Four-to-five specialist agents review it in parallel, a policy agent scores it, and a coordinator writes the verdict to a Google Sheet (vendor mode) or Google Doc deal memo (M&A mode).

| Demo | Mode | Findings | Verdict | Risk score |
|---|---|---:|---|---:|
| **Acme Cloud Analytics** — `examples/tprm/acme/` | vendor | 27 | reject | 171 |
| **HashiCorp Inc.** — `examples/tprm/hashicorp/` | M&A | 55 | reject | 700 |

Both numbers come from real Gemini 2.5 Flash runs recorded into `examples/tprm/*/replay.jsonl` — you can replay them offline with no API keys.

## Quick start

```bash
git clone https://github.com/songyinggoh/Orchestra-TPRM.git
cd Orchestra-TPRM
pip install -e ".[tprm,server,storage,telemetry]"
```

**Terminal 1 — backend**

```bash
uvicorn orchestra_tprm.server.app:app --host 0.0.0.0 --port 8080
```

**Terminal 2 — dashboard**

```bash
cd dashboard && npm install && npm run dev
```

Open **http://localhost:3000**, pick a demo preset (or paste a Google Drive folder URL), and click **Run Assessment**.

No API keys needed for demos — the bundled replay packets replay pre-recorded Gemini responses deterministically.

### Live run against real documents

Set your Google credentials and point the dashboard at a Drive folder:

```bash
export GOOGLE_API_KEY=AIza...
export GOOGLE_CLOUD_PROJECT=my-project
```

In the dashboard, select **Google Drive folder**, paste the folder URL (the service account must have Viewer access), enter the subject name, and run. The pipeline streams live progress via SSE and writes findings to BigQuery + a Google Sheet or Doc.

See [docs/developer.md](./docs/developer.md) for CLI flags, replay recording, and local test modes.

## Architecture

```
                ┌───────────┐
                │ bootstrap │
                └─────┬─────┘
                      │
                ┌─────▼─────┐
                │  intake   │   resolves manifest, materializes URIs
                └─────┬─────┘
                      │
                ┌─────▼─────┐
                │  router   │   gemini-2.5-flash, routes docs → specialists
                └─────┬─────┘
                      │ parallel fan-out
       ┌──────────┬───┴────┬──────────┬─────────────┐
       ▼          ▼        ▼          ▼             ▼
   ┌───────┐ ┌────────┐ ┌──────┐ ┌─────────┐ ┌───────────┐
   │ legal │ │security│ │ code │ │external │ │ financial │ (M&A only)
   └───┬───┘ └───┬────┘ └──┬───┘ └────┬────┘ └─────┬─────┘
       └────────┴──────────┴──────────┴────────────┘
                      │ join
                ┌─────▼─────┐
                │  policy   │   scores findings, applies policy pack
                └─────┬─────┘
                      │
                ┌─────▼──────┐
                │coordinator │   Sheet (vendor) or Doc (M&A)
                └─────┬──────┘
                      │
                     END
```

| Layer | Tech |
|---|---|
| LLM | Gemini 2.5 Flash via Google AI Studio (free tier) or Gemini CLI subscription |
| Backend | FastAPI + Server-Sent Events for live progress |
| Frontend | React 19 + Vite + TypeScript |
| Orchestration | Orchestra framework (typed state, parallel fan-out, compile-time graph validation) |
| Storage | SQLite (events, dev) · Cloud SQL Postgres + BigQuery (production) |
| Outputs | Google Sheets · Google Docs · BigQuery findings table |
| Deploy | Cloud Run + Pub/Sub + Cloud Trace |

## Repository layout

```
src/orchestra/          — framework (fork of songyinggoh/Orchestra)
src/orchestra_tprm/     — TPRM application
  ├─ agents/            — intake, router, policy, coordinator, specialists/
  ├─ adapters/          — Drive, Sheets, Docs, BigQuery, GitHub, GeminiFiles
  ├─ modes/             — vendor.yaml, ma.yaml (mode + policy packs)
  ├─ server/app.py      — FastAPI + SSE
  └─ cli.py             — orchestra-tprm entry point
dashboard/              — React 19 + Vite dashboard
examples/tprm/          — demo packets + recorded replay JSONLs
tests/tprm/             — 243 tests (unit + integration)
.github/workflows/      — CI (lint, type-check, security, unit, TPRM, UI builds)
```

## Modes

Two YAML-defined modes share the same graph; only the active specialists and output kind differ.

**`vendor`** — vendor onboarding review. Specialists: `legal`, `security`, `code`, `external`. Coordinator writes findings to a Google Sheet.

**`ma`** — M&A due-diligence review. Specialists: `legal`, `security`, `code`, `external`, `financial`. Coordinator writes a structured deal memo (Executive Summary, Strategic Fit, Risk Areas, Recommended Conditions) to a Google Doc.

Both modes use `gemini-2.5-flash` for all agents. Concurrency: `Semaphore(5)` so the five specialists run in parallel (configurable via `GEMINI_CLI_CONCURRENCY`).

## Tests + CI

```bash
pytest tests/tprm/ -q   # 243 passed, 8 skipped (~90s)
```

GitHub Actions runs on every push/PR:
- **lint** — ruff check + format
- **type-check** — mypy (non-blocking; tracked debt)
- **security** — gitleaks + bandit (SAST) + pip-audit (SCA)
- **unit-test** — 3 OS × 3 Python versions matrix
- **tprm-test** — TPRM suite on Linux/Py3.12
- **ui-build** — both the framework UI and the TPRM dashboard
- **integration-test** — Postgres + Redis + NATS services

## Credits

Built on the [Orchestra](https://github.com/songyinggoh/Orchestra) multi-agent framework — typed state with reducers, compile-time graph validation, parallel fan-out, scripted-LLM test harness, and seven LLM provider backends.

## License

[Apache 2.0](./LICENSE)
