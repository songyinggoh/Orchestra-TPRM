"""Invariant 1 — No `if mode ==` branches in specialist agents.

Specialists must be mode-agnostic. Any mode-specific behavior belongs in
configuration (vendor.yaml / ma.yaml), not in Python conditionals. This
test scans the specialist tree for forbidden mode-discriminator patterns.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SPECIALISTS_DIR = REPO_ROOT / "src" / "orchestra_tprm" / "agents" / "specialists"

# Forbidden patterns — any of these in a specialist source file is a violation.
FORBIDDEN_PATTERNS = [
    re.compile(r"\bif\s+mode\s*==\s*['\"]"),
    re.compile(r"\bif\s+mode\s+in\s*[\(\[\{]"),
    re.compile(r"\bmode\s*==\s*['\"](vendor|ma|vendor_onboarding|m_and_a)['\"]"),
    re.compile(r"\belif\s+mode\s*==\s*['\"]"),
]


def _collect_specialist_files() -> list[Path]:
    if not SPECIALISTS_DIR.exists():
        return []
    return [p for p in SPECIALISTS_DIR.rglob("*.py") if p.name != "__init__.py"]


def test_specialists_have_no_mode_conditional_branches():
    # Arrange
    files = _collect_specialist_files()
    if not files:
        # Vacuously pass — specialists not yet written.
        print(f"[invariant-1] No specialist files found under {SPECIALISTS_DIR}; passing vacuously.")
        return

    # Act
    violations: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern in FORBIDDEN_PATTERNS:
                if pattern.search(line):
                    rel = path.relative_to(REPO_ROOT)
                    violations.append(f"{rel}:{lineno}: {stripped}")

    # Assert
    assert not violations, (
        "Specialist agents must not branch on `mode`. Move mode-specific logic to "
        "config (vendor.yaml/ma.yaml). Violations:\n  " + "\n  ".join(violations)
    )
