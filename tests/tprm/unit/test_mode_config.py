"""ModeConfig: declarative per-mode behavior. Coordinator/PolicyAgent/specialists
must remain free of `if mode ==` literals — all variability lives here."""
from __future__ import annotations

import pytest

from orchestra_tprm.modes.config import ModeConfig, load_mode


def test_load_vendor_mode():
    cfg = load_mode("vendor")
    assert cfg.name == "vendor"
    assert cfg.specialists.legal == "gemini-2.5-flash"
    assert cfg.specialists.financial is None  # vendor skips financial
    assert cfg.coordinator_template.endswith("coordinator_vendor.tmpl")
    assert cfg.policy_pack.endswith("vendor.yaml")
    assert cfg.output_kind == "sheet"


def test_load_ma_mode():
    cfg = load_mode("ma")
    assert cfg.name == "ma"
    assert cfg.specialists.legal == "gemini-2.5-pro"
    assert cfg.specialists.financial == "gemini-2.5-pro"
    assert cfg.coordinator_template.endswith("coordinator_ma.tmpl")
    assert cfg.output_kind == "doc"


def test_unknown_mode_raises():
    with pytest.raises(FileNotFoundError):
        load_mode("nonexistent")
