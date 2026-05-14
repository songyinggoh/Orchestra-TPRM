"""Invariant 4 — Never combine `stream=True` with `tools=...` in the same call.

Gemini (and most function-calling LLM APIs) does not support streaming
when tools are passed. Any call site that sets both is a latent
runtime failure. Scan the TPRM source tree for violations.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
TPRM_DIR = REPO_ROOT / "src" / "orchestra_tprm"


def _collect_py_files() -> list[Path]:
    if not TPRM_DIR.exists():
        return []
    return list(TPRM_DIR.rglob("*.py"))


def _kwarg_is_true(call: ast.Call, name: str) -> bool:
    for kw in call.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return True
    return False


def _has_kwarg(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name for kw in call.keywords)


def test_no_call_combines_streaming_with_tools():
    # Arrange
    files = _collect_py_files()
    if not files:
        pytest.skip(f"{TPRM_DIR} has no .py files; invariant vacuous.")

    # Act
    violations: list[str] = []
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # Only inspect calls that look like LLM invocations.
            func = node.func
            method_name = func.attr if isinstance(func, ast.Attribute) else (
                func.id if isinstance(func, ast.Name) else None
            )
            if method_name not in {"complete", "stream", "generate", "generate_content"}:
                continue
            if _kwarg_is_true(node, "stream") and _has_kwarg(node, "tools"):
                rel = path.relative_to(REPO_ROOT)
                violations.append(f"{rel}:{node.lineno}: {method_name}(..., stream=True, tools=...)")

    # Assert
    assert not violations, (
        "Streaming with tools is unsupported by Gemini. Disable streaming "
        "whenever tools are passed. Violations:\n  " + "\n  ".join(violations)
    )
