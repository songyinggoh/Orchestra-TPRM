"""orchestra-tprm CLI -- single entry point for both vendor and M&A modes.

Builds the per-mode adapter bundle from the ``--local`` flag (Fake* adapters
for offline runs; real Drive/Sheets/Docs/BQ/GitHub clients otherwise) and
hands them to :func:`build_graph`. The resulting CompiledGraph is then
executed via the standard Orchestra runner.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional

import typer
import yaml

from orchestra.core.runner import run as run_graph
from orchestra.testing import ScriptedLLM
from orchestra.core.types import LLMResponse

from orchestra_tprm.adapters.bigquery import BigQueryAdapter, FakeBigQueryAdapter
from orchestra_tprm.adapters.docs import DocsAdapter, FakeDocsAdapter
from orchestra_tprm.adapters.drive import DriveAdapter, FakeDriveAdapter
from orchestra_tprm.adapters.gemini_files import (
    GeminiFilesAdapter,
    GeminiFilesAdapterReal,
)
from orchestra_tprm.adapters.github import FakeGitHubAdapter, GitHubAdapter
from orchestra_tprm.adapters.sheets import FakeSheetsAdapter, SheetsAdapter
from orchestra_tprm.graph import Adapters, build_graph
from orchestra_tprm.modes.config import load_mode

app = typer.Typer(add_completion=False, help="Multi-agent TPRM framework.")


async def _run_and_maybe_record(
    graph: Any,
    initial: dict,
    provider: Any,
    persist: bool,
    record_replay: Optional[Path],
) -> Any:
    """Run the graph and optionally export LLMCalled events to a JSONL replay file."""
    result = await run_graph(graph, input=initial, provider=provider, persist=persist)

    if record_replay is not None and persist:
        from orchestra.storage.events import EventType
        from orchestra.storage.sqlite import SQLiteEventStore

        async with SQLiteEventStore() as store:
            events = await store.get_events(
                result.run_id,
                event_types=[EventType.LLM_CALLED],
            )
        lines = [json.dumps(e.model_dump(), default=str) for e in events]
        record_replay.write_text("\n".join(lines), encoding="utf-8")
        typer.echo(f"Recorded {len(lines)} LLM calls → {record_replay}")

    return result


def _load_env() -> dict[str, str]:
    """Best-effort .env loader (does not overwrite os.environ)."""
    out = dict(os.environ)
    p = Path(".env")
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out.setdefault(k.strip(), v.strip())
    return out


def _stub_local_provider() -> ScriptedLLM:
    """Local-mode fallback provider when no real LLM is configured.

    Returns a large pool of empty/no-op JSON responses so the graph can
    complete deterministically without making any network calls. Used by
    smoke tests and ``--local`` runs that don't have GOOGLE_API_KEY set.
    """
    pool = [
        LLMResponse(content="[]"),
        LLMResponse(content="{}"),
        LLMResponse(content=""),
    ] * 20
    return ScriptedLLM(pool)


def _resolve_provider(env: dict[str, str], replay: Optional[Path]):
    """Pick the best available LLM provider for the current run.

    Order: ``--replay`` file > GOOGLE_API_KEY > local stub.
    """
    if replay is not None:
        from orchestra.providers.replay import ReplayProvider  # ImportError bubbles — never silently run live on --replay
        return ReplayProvider.from_jsonl(str(replay))
    if env.get("GOOGLE_API_KEY"):
        from orchestra.providers.google import GoogleProvider

        return GoogleProvider(api_key=env["GOOGLE_API_KEY"])
    return _stub_local_provider()


@app.command()
def main(
    mode: str = typer.Option(..., "--mode", help="vendor | ma"),
    packet: Path = typer.Option(..., "--packet", help="Path to packet directory"),
    local: bool = typer.Option(False, "--local", help="Use Fake* adapters; no Google API"),
    out: Path = typer.Option(Path("verdict.json"), "--out"),
    record_replay: Optional[Path] = typer.Option(None, "--record-replay"),
    replay: Optional[Path] = typer.Option(None, "--replay"),
    dashboard: bool = typer.Option(True, "--dashboard/--no-dashboard"),
) -> None:
    env = _load_env()
    cfg = load_mode(mode)

    manifest_path = packet / "manifest.yaml"
    manifest = (
        yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {}
    )

    # Extract optional github_url from links.txt (first non-empty line).
    github_url = ""
    links_rel = manifest.get("links_file", "links.txt")
    links_path = packet / links_rel
    if links_path.exists():
        for line in links_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped:
                github_url = stripped
                break

    if local:
        provider = _resolve_provider(env, replay) if replay is not None else _stub_local_provider()
        drive = FakeDriveAdapter()
        files = GeminiFilesAdapter()
        sheets = FakeSheetsAdapter()
        docs = FakeDocsAdapter()
        bq = FakeBigQueryAdapter()
        github = FakeGitHubAdapter()
        drive_folder_id = ""
        sheet_id = env.get("SHEETS_VENDOR_TEMPLATE_ID", "VENDOR-LOCAL")
        doc_id = env.get("DOCS_MA_TEMPLATE_ID", "")
    else:
        from orchestra.providers.gemini_cli import GeminiCliProvider

        provider = GeminiCliProvider()
        drive = DriveAdapter()
        files = GeminiFilesAdapter()  # text-based docs use local:// URIs; no Files API upload needed
        sheets = SheetsAdapter()
        docs = DocsAdapter()
        bq = BigQueryAdapter(project=env.get("GOOGLE_CLOUD_PROJECT"))
        github = GitHubAdapter(token=env.get("GITHUB_TOKEN"))
        drive_folder_id = (
            env.get("DRIVE_VENDOR_FOLDER_ID", "")
            if cfg.name == "vendor"
            else env.get("DRIVE_MA_FOLDER_ID", "")
        )
        sheet_id = env.get("SHEETS_VENDOR_TEMPLATE_ID", "")
        doc_id = env.get("DOCS_MA_TEMPLATE_ID", "")

    adapters = Adapters(
        drive=drive, files=files, sheets=sheets, docs=docs, bq=bq, github=github
    )
    graph = build_graph(
        cfg,
        adapters=adapters,
        drive_folder_id=drive_folder_id,
        sheet_id=sheet_id,
        doc_id=doc_id,
        bq_dataset=env.get("BQ_DATASET", "tprm_audit"),
        bq_table=env.get("BQ_TABLE", "tprm_findings"),
        github_url=github_url,
    )

    initial: dict = {
        "mode": cfg.name,
        "subject_name": manifest.get("subject_name", ""),
        "packet_path": str(packet),
    }
    persist = record_replay is not None
    result = asyncio.run(
        _run_and_maybe_record(graph, initial, provider, persist, record_replay)
    )
    state = result.state
    payload = {
        "mode": state.get("mode"),
        "subject_name": state.get("subject_name"),
        "policy_verdict": state.get("policy_verdict"),
        "risk_score": state.get("risk_score"),
        "verdict_doc_id": state.get("verdict_doc_id"),
        "verdict_local_path": state.get("verdict_local_path", ""),
        "findings": [
            f if isinstance(f, dict) else f.model_dump()
            for f in state.get("findings", [])
        ],
    }
    out.write_text(json.dumps(payload, indent=2, default=str))
    typer.echo(f"Wrote {out}")
