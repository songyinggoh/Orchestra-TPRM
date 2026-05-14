"""Invariant 3 — Every `add_node(...)` call in build_graph passes `output_key=`.

Implicit output keys make state merges fragile and mode-coupled. The
TPRM graph builder must always pass an explicit `output_key=` kwarg
so reducers know exactly which state field each node writes to.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GRAPH_PY = REPO_ROOT / "src" / "orchestra_tprm" / "graph.py"


def _find_add_node_calls(tree: ast.AST) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "add_node":
            calls.append(node)
    return calls


def _call_has_kwarg(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name for kw in call.keywords)


def test_every_add_node_call_has_explicit_output_key():
    # Arrange
    if not GRAPH_PY.exists():
        pytest.skip(f"{GRAPH_PY.relative_to(REPO_ROOT)} not yet written; invariant deferred.")

    source = GRAPH_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(GRAPH_PY))
    add_node_calls = _find_add_node_calls(tree)

    if not add_node_calls:
        pytest.skip("graph.py exists but contains no add_node calls yet.")

    # Act
    violations: list[str] = []
    for call in add_node_calls:
        if not _call_has_kwarg(call, "output_key"):
            # Best-effort node-name extraction for the error message.
            node_name = "?"
            if call.args and isinstance(call.args[0], ast.Constant):
                node_name = repr(call.args[0].value)
            violations.append(f"graph.py:{call.lineno}: add_node({node_name}, ...) missing output_key=")

    # Assert
    assert not violations, (
        "Every add_node(...) call in build_graph() must pass an explicit "
        "output_key= kwarg. Violations:\n  " + "\n  ".join(violations)
    )
