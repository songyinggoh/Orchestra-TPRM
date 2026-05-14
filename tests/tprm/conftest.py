"""Shared fixtures for TPRM tests."""
from __future__ import annotations

import pytest

from orchestra_tprm.schemas import Citation, Finding


@pytest.fixture
def sample_finding() -> Finding:
    return Finding(
        agent="LegalAgent",
        category="liability",
        severity="high",
        summary="Liability cap is 1× annual fees, below 12-month industry norm.",
        evidence=[Citation(file_id="msa.pdf", page=12, snippet="liability shall be limited...")],
        raw={"clause_id": "8.2", "cap_usd": 50000},
    )
