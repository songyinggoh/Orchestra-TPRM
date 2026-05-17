# Developer Reference

This document covers the `orchestra-tprm` CLI, provider selection, replay recording, and local test modes. For the end-user web interface see the [README quick start](../README.md#quick-start).

## Installation

```bash
pip install -e ".[tprm,server,storage,telemetry]"
```

## CLI usage

```
orchestra-tprm --mode <vendor|ma> --packet <path> [options]
```

| Flag | Description |
|---|---|
| `--mode vendor\|ma` | Assessment type (required) |
| `--packet <path>` | Directory containing `manifest.yaml` and documents (required) |
| `--replay <file.jsonl>` | Replay pre-recorded LLM responses — no API key needed |
| `--record-replay <file.jsonl>` | Record a live run to JSONL for future replay |
| `--local` | Use `ScriptedLLM` stub — hermetic, no network, for tests |
| `--subject <name>` | Override subject name (default: value in manifest.yaml) |

## Provider resolution order

The CLI (and server backend) picks the LLM backend in this order:

1. `--replay <file.jsonl>` → deterministic offline replay via `_ReplayProvider`
2. `--local` (no replay) → `ScriptedLLM` stub — all responses return empty strings
3. `GOOGLE_API_KEY` env var → `GoogleProvider` (AI Studio REST API)
4. `gemini` CLI on PATH → `GeminiCliProvider` (Gemini CLI subscription)

The FastAPI server (`server/app.py`) follows the same priority: if `GOOGLE_API_KEY` is set it uses `GoogleProvider`; otherwise it falls back to `GeminiCliProvider`.

## Offline demos (no API key)

Pre-recorded replay JSONLs are bundled in `examples/tprm/`:

```bash
# Vendor demo — 27 findings, reject, risk score 171
orchestra-tprm --mode vendor --packet examples/tprm/acme \
  --replay examples/tprm/acme/replay.jsonl

# M&A demo — 55 findings, reject, risk score 700
orchestra-tprm --mode ma --packet examples/tprm/hashicorp \
  --replay examples/tprm/hashicorp/replay.jsonl
```

The dashboard can also run these: start the server normally (no env vars needed) and select the matching **Demo preset** in the form.

## Recording a new replay

```bash
export GOOGLE_API_KEY=AIza...
orchestra-tprm --mode vendor --packet examples/tprm/acme \
  --record-replay examples/tprm/acme/replay.jsonl
```

`_RecordingProvider` intercepts every `provider.complete()` call and serializes prompt + response to JSONL. Commit the file to make CI replays deterministic.

## Running tests

```bash
pytest tests/tprm/ -q          # 243 unit tests, ~90 s
pytest tests/tprm/ -q -k live  # live tests (needs GOOGLE_API_KEY)
```

The full CI matrix (lint, type-check, security, unit, TPRM, UI build, integration) runs on every push via `.github/workflows/`.

## Packet format

A packet directory must contain `manifest.yaml`:

```yaml
subject: Acme Cloud Analytics
documents:
  - path: soc2.pdf
    type: compliance
  - url: https://github.com/acme/platform
    type: code
  - path: msa.pdf
    type: legal
```

`path` entries are resolved relative to the packet directory. `url` entries are fetched by the intake agent. Optionally, create `links.txt` with one URL per line — the first non-empty line is used as the GitHub repo URL passed to `CodeAgent`.

## Environment variables

| Variable | Purpose |
|---|---|
| `GOOGLE_API_KEY` | Google AI Studio key — enables real Gemini calls |
| `GOOGLE_CLOUD_PROJECT` | GCP project — enables BigQuery, Cloud SQL, Drive |
| `GITHUB_TOKEN` | GitHub PAT — enables private repo scanning |
| `SHEETS_VENDOR_TEMPLATE_ID` | Google Sheets template to clone for vendor verdicts |
| `DOCS_MA_TEMPLATE_ID` | Google Docs template to clone for M&A deal memos |
| `DRIVE_VENDOR_FOLDER_ID` | Drive folder for vendor verdict files |
| `DRIVE_MA_FOLDER_ID` | Drive folder for M&A verdict files |
| `BQ_DATASET` | BigQuery dataset name (default: `tprm_audit`) |
| `BQ_TABLE` | BigQuery table name (default: `tprm_findings`) |
| `GEMINI_CLI_CONCURRENCY` | Max parallel Gemini CLI calls (default: `5`) |
