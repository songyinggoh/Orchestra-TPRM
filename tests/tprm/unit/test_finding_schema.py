"""Finding/Citation schema — must round-trip through JSON, sort by severity,
and pass the Gemini-schema converter."""
from __future__ import annotations

import json

import pytest

from orchestra.providers._gemini_schema import pydantic_to_gemini_schema
from orchestra_tprm.schemas import Citation, Finding, Severity


def test_finding_round_trip():
    f = Finding(
        agent="LegalAgent",
        category="liability",
        severity="high",
        summary="Cap below industry norm.",
        evidence=[Citation(file_id="msa.pdf", page=12, snippet="liability cap...")],
        raw={"clause_id": "8.2"},
    )
    blob = f.model_dump_json()
    parsed = Finding.model_validate_json(blob)
    assert parsed == f


def test_finding_passes_gemini_schema_converter():
    schema = pydantic_to_gemini_schema(Finding)
    assert schema["type"] == "object"
    assert set(schema["required"]) >= {"agent", "category", "severity", "summary"}
    sev = schema["properties"]["severity"]
    assert sorted(sev["enum"]) == ["critical", "high", "low", "medium"]


def test_severity_ordering():
    assert Severity.LOW < Severity.MEDIUM < Severity.HIGH < Severity.CRITICAL


def test_citation_offset_xor_page_allowed():
    # Plain text → use offset; PDF → use page; allow either or neither.
    Citation(file_id="x.txt", offset=42, snippet="...")
    Citation(file_id="x.pdf", page=3, snippet="...")
    Citation(file_id="x", snippet="...")


def test_finding_row_round_trip():
    from orchestra_tprm.storage.models import FindingRow
    f = Finding(
        agent="LegalAgent",
        category="liability",
        severity="high",
        summary="cap low",
        evidence=[Citation(file_id="msa.pdf", document_id=42, page=12, snippet="...")],
        raw={"clause": "8.2"},
    )
    row = FindingRow.from_finding("run-xyz", f)
    assert row.run_id == "run-xyz"
    assert row.agent_name == "LegalAgent"
    assert row.citations[0]["document_id"] == 42
    assert row.payload["clause"] == "8.2"
