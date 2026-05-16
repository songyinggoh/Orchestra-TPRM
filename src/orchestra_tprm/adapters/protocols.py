"""Adapter Protocol interfaces — structural typing for unit-test injection.

Each ``Fake*`` adapter in this package satisfies its matching Protocol via
duck typing. No ``isinstance`` checks are performed at runtime.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from orchestra_tprm.schemas import Finding


@runtime_checkable
class BigQueryAdapterP(Protocol):
    """Minimal surface that ``PolicyAgent`` requires from any BQ adapter."""

    async def append_findings(
        self,
        dataset: str,
        table: str,
        run_id: str,
        findings: list[Finding],
        *,
        mode: str = "",
        subject: str = "",
    ) -> int:
        """Append findings to a BQ table. Returns number of rows written."""
        ...
