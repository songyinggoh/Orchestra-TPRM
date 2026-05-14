"""orchestra-tprm CLI — single entry point for both vendor and M&A modes."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
import yaml

from orchestra.core.runner import run as run_graph
from orchestra_tprm.graph import build_graph
from orchestra_tprm.modes.config import load_mode

app = typer.Typer(add_completion=False, help="Multi-agent TPRM framework.")


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
    cfg = load_mode(mode)
    manifest_path = packet / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    initial: dict = {
        "mode": cfg.name,
        "subject_name": manifest.get("subject_name", ""),
        "packet_path": str(packet),
    }
    graph = build_graph(cfg)
    result = asyncio.run(
        run_graph(graph, input=initial, persist=False)
    )
    # result.state is a plain dict[str, Any]
    state = result.state
    payload = {
        "mode": state.get("mode"),
        "subject_name": state.get("subject_name"),
        "findings": [
            f if isinstance(f, dict) else f.model_dump()
            for f in state.get("findings", [])
        ],
        "verdict_local_path": state.get("verdict_local_path", ""),
    }
    out.write_text(json.dumps(payload, indent=2, default=str))
    typer.echo(f"Wrote {out}")
