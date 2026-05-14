"""Invariant 5 — Coordinator and policy modules contain no hardcoded mode names.

The Coordinator and policy layers must be mode-agnostic. All mode-specific
behavior arrives through injected configuration, never via literals like
`"vendor"` or `"ma"` in the source code.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENTS_DIR = REPO_ROOT / "src" / "orchestra_tprm" / "agents"
COORDINATOR_PY = AGENTS_DIR / "coordinator.py"
POLICY_PY = AGENTS_DIR / "policy.py"

# Hardcoded mode-name literals (with surrounding quotes) that must not appear.
FORBIDDEN_LITERALS = {"vendor", "ma", "vendor_onboarding", "m_and_a"}
LITERAL_RE = re.compile(
    r"""['"](vendor|ma|vendor_onboarding|m_and_a)['"]"""
)


def _scan_file(path: Path) -> list[str]:
    violations: list[str] = []
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Strip inline comments before matching.
        code_part = line.split("#", 1)[0]
        for match in LITERAL_RE.finditer(code_part):
            if match.group(1) in FORBIDDEN_LITERALS:
                rel = path.relative_to(REPO_ROOT)
                violations.append(f"{rel}:{lineno}: literal {match.group(0)} in `{stripped}`")
    return violations


def test_coordinator_has_no_hardcoded_mode_names():
    if not COORDINATOR_PY.exists():
        pytest.skip(f"{COORDINATOR_PY.relative_to(REPO_ROOT)} not yet written.")

    violations = _scan_file(COORDINATOR_PY)

    assert not violations, (
        "coordinator.py must not contain hardcoded mode names — inject mode via config. "
        "Violations:\n  " + "\n  ".join(violations)
    )


def test_policy_has_no_hardcoded_mode_names():
    if not POLICY_PY.exists():
        pytest.skip(f"{POLICY_PY.relative_to(REPO_ROOT)} not yet written.")

    violations = _scan_file(POLICY_PY)

    assert not violations, (
        "policy.py must not contain hardcoded mode names — inject mode via config. "
        "Violations:\n  " + "\n  ".join(violations)
    )
