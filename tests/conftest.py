"""Shared test fixtures for Orchestra test suite."""

import sys
from pathlib import Path

import pytest

# Ensure this worktree's src/ wins over any editable install pointing
# at a sibling working tree (e.g. ../Orchestra/). Without this, tests
# import the parent tree's modules and never see local edits.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture(autouse=True)
def isolate_orchestra_db(tmp_path, monkeypatch):
    """Route every test's SQLite store to a per-test temp directory.

    Prevents 'database is locked' errors when tests run in parallel or
    when a previous test left an uncommitted WAL transaction.
    """
    db_path = str(tmp_path / "test_runs.db")
    monkeypatch.setenv("ORCHESTRA_DB_PATH", db_path)
