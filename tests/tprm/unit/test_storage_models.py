"""Unit tests for SQLAlchemy storage models (no live DB required)."""
from __future__ import annotations

import pytest


def test_models_importable() -> None:
    """All ORM classes must be importable without a database connection."""
    from orchestra_tprm.storage.models import (  # noqa: F401
        AuditEvent,
        Base,
        Chunk,
        Document,
        FindingRow,
        Vendor,
    )


def test_base_has_all_tables() -> None:
    """Base.metadata must declare exactly the five expected tables."""
    from orchestra_tprm.storage.models import Base

    assert set(Base.metadata.tables.keys()) == {
        "vendors",
        "documents",
        "chunks",
        "findings",
        "audit_events",
    }


def test_vendor_table_columns() -> None:
    """Vendor ORM model must expose expected column names."""
    from orchestra_tprm.storage.models import Vendor

    col_names = {c.name for c in Vendor.__table__.columns}
    assert {"id", "name", "mode", "metadata", "created_at", "updated_at"} <= col_names


def test_chunk_embedding_column_exists() -> None:
    """Chunk must have an 'embedding' column (pgvector type or LargeBinary fallback)."""
    from orchestra_tprm.storage.models import Chunk

    col_names = {c.name for c in Chunk.__table__.columns}
    assert "embedding" in col_names


def test_finding_row_from_finding_factory() -> None:
    """FindingRow.from_finding() must map Pydantic Finding fields correctly."""
    from orchestra_tprm.schemas import Citation, Finding
    from orchestra_tprm.storage.models import FindingRow

    finding = Finding(
        agent="legal",
        category="contract_risk",
        severity="high",
        summary="Indemnity clause missing",
        evidence=[Citation(file_id="f1", snippet="clause 4.1")],
        raw={"score": 0.9},
    )
    row = FindingRow.from_finding("run-001", finding)
    assert row.run_id == "run-001"
    assert row.agent_name == "legal"
    assert row.severity == "high"
    assert row.citations[0]["file_id"] == "f1"


# ── Live-DB tests (deferred) ──────────────────────────────────────────────────

@pytest.mark.skip(reason="requires live Postgres — run after Cloud SQL provisioning")
async def test_vendor_round_trip_insert_select() -> None:
    """Insert a Vendor row and read it back via async session."""
    pass  # implement after Cloud SQL is provisioned


@pytest.mark.skip(reason="requires live Postgres — run after Cloud SQL provisioning")
async def test_document_round_trip_insert_select() -> None:
    """Insert a Document row and read it back via async session."""
    pass


@pytest.mark.skip(reason="requires live Postgres — run after Cloud SQL provisioning")
async def test_chunk_round_trip_insert_select() -> None:
    """Insert a Chunk row with a real embedding and read it back."""
    pass


@pytest.mark.skip(reason="requires live Postgres — run after Cloud SQL provisioning")
async def test_finding_row_round_trip_insert_select() -> None:
    """Insert a FindingRow and read it back via async session."""
    pass


@pytest.mark.skip(reason="requires live Postgres — run after Cloud SQL provisioning")
async def test_audit_event_round_trip_insert_select() -> None:
    """Insert an AuditEvent and read it back via async session."""
    pass
