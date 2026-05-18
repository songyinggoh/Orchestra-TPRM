"""End-to-end stub run: CLI invokes a graph of stub nodes that all return
empty findings, just to prove wiring works."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

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


# ---------------------------------------------------------------------------
# WR-09: gemini CLI PATH guard
# ---------------------------------------------------------------------------

def test_gemini_missing_live_mode(tmp_path: Path):
    """No gemini on PATH, no GOOGLE_API_KEY → exit 1 with actionable message."""
    runner = CliRunner(mix_stderr=True)
    with (
        patch("shutil.which", return_value=None),
        patch("orchestra_tprm.cli._load_env", return_value={}),
    ):
        result = runner.invoke(
            app,
            [
                "--mode", "vendor",
                "--packet", "examples/tprm/acme",
                "--out", str(tmp_path / "out.json"),
                "--no-dashboard",
            ],
        )
    assert result.exit_code == 1
    output = result.output.lower()
    assert "gemini" in output
    assert "not found" in output


def test_gemini_missing_record_replay(tmp_path: Path):
    """No gemini on PATH with --record-replay → exit 1 mentioning record-replay."""
    runner = CliRunner(mix_stderr=True)
    with (
        patch("shutil.which", return_value=None),
        patch("orchestra_tprm.cli._load_env", return_value={}),
    ):
        result = runner.invoke(
            app,
            [
                "--mode", "vendor",
                "--packet", "examples/tprm/acme",
                "--record-replay", str(tmp_path / "replay.jsonl"),
                "--out", str(tmp_path / "out.json"),
                "--no-dashboard",
            ],
        )
    assert result.exit_code == 1
    assert "record-replay" in result.output.lower()


def test_gemini_present_proceeds_past_check(tmp_path: Path):
    """When gemini is on PATH the guard passes and provider construction is attempted."""
    runner = CliRunner(mix_stderr=True)
    with (
        patch("shutil.which", return_value="/usr/bin/gemini"),
        patch("orchestra_tprm.cli._load_env", return_value={}),
        patch(
            "orchestra.providers.gemini_cli.GeminiCliProvider",
            side_effect=RuntimeError("stop-here-sentinel"),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "--mode", "vendor",
                "--packet", "examples/tprm/acme",
                "--out", str(tmp_path / "out.json"),
                "--no-dashboard",
            ],
        )
    # Must NOT have exited via the PATH-check message
    assert "not found on path" not in result.output.lower()
    # Must have reached provider construction (sentinel proves it)
    sentinel_hit = (
        "stop-here-sentinel" in result.output
        or (result.exception is not None and "stop-here-sentinel" in str(result.exception))
    )
    assert sentinel_hit
