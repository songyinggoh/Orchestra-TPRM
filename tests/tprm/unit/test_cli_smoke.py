"""End-to-end stub run: CLI invokes a graph of stub nodes that all return
empty findings, just to prove wiring works."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from orchestra_tprm.cli import app


def test_cli_smoke_vendor_local(tmp_path: Path):
    runner = CliRunner()
    out_path = tmp_path / "out.json"
    result = runner.invoke(
        app,
        [
            "--mode", "vendor",
            "--packet", "examples/tprm/acme",
            "--local",
            "--out", str(out_path),
            "--no-dashboard",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(out_path.read_text())
    assert payload["mode"] == "vendor"
    assert payload["subject_name"]
    assert "findings" in payload
