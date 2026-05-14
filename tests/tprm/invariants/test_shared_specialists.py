"""Invariant 2 — Vendor and M&A modes share specialist classes by import path.

Every specialist class referenced in `vendor.yaml` must also appear in
`ma.yaml` under the same fully-qualified import path. Duplicating specialist
implementations across modes is forbidden — modes differ in configuration
(prompts, thresholds, routing), not in class identity.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MODES_DIR = REPO_ROOT / "src" / "orchestra_tprm" / "modes"
VENDOR_YAML = MODES_DIR / "vendor.yaml"
MA_YAML = MODES_DIR / "ma.yaml"

# Match `class: orchestra_tprm.agents.specialists.<...>` or quoted variants.
# Fully-qualified import paths starting with the project package.
CLASS_PATH_RE = re.compile(
    r"""(?:class|target|specialist|agent_class)\s*:\s*['"]?"""
    r"""(orchestra_tprm\.[A-Za-z0-9_.]+)['"]?""",
    re.IGNORECASE,
)


def _extract_specialist_paths(yaml_path: Path) -> set[str]:
    text = yaml_path.read_text(encoding="utf-8")
    matches = CLASS_PATH_RE.findall(text)
    # Keep only paths under the specialists package.
    return {m for m in matches if ".agents.specialists." in m}


def test_vendor_and_ma_share_specialist_classes_by_import_path():
    # Arrange
    if not VENDOR_YAML.exists() or not MA_YAML.exists():
        pytest.skip(
            f"Mode configs not yet written (vendor={VENDOR_YAML.exists()}, "
            f"ma={MA_YAML.exists()}); invariant cannot be checked."
        )

    vendor_paths = _extract_specialist_paths(VENDOR_YAML)
    ma_paths = _extract_specialist_paths(MA_YAML)

    if not vendor_paths and not ma_paths:
        pytest.skip("Neither mode references specialists yet; invariant vacuous.")

    # Act
    only_in_vendor = vendor_paths - ma_paths
    only_in_ma = ma_paths - vendor_paths

    # Assert — every specialist class referenced in one mode must appear in the other.
    assert not only_in_vendor and not only_in_ma, (
        "Specialist classes must be SHARED across vendor.yaml and ma.yaml "
        "(reuse, not duplicate). Divergent imports:\n"
        f"  only in vendor.yaml: {sorted(only_in_vendor)}\n"
        f"  only in ma.yaml:     {sorted(only_in_ma)}"
    )
