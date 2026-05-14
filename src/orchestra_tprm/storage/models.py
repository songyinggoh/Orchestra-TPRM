"""SQLAlchemy ORM models for TPRM durable state.

Tables
------
vendors        — one row per vendor / M&A target being evaluated
documents      — one row per uploaded document within a run
chunks         — pgvector-indexed text chunks derived from documents
findings       — agent-level findings (FindingRow avoids collision with schemas.Finding)
audit_events   — append-only event log for observability / compliance
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# pgvector type — imported lazily so the module is importable without pgvector
# installed (unit tests only need the ORM metadata, not a live DB).
try:
    from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover — pgvector optional at import time
    from sqlalchemy import LargeBinary as Vector  # type: ignore[assignment]


class Base(DeclarativeBase):
    """Shared declarative base — used by Alembic env.py."""
    pass


# ── Vendor ────────────────────────────────────────────────────────────────────

class Vendor(Base):
    """One row per vendor or M&A target under evaluation."""

    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # "vendor" | "ma"
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    documents: Mapped[list["Document"]] = relationship("Document", back_populates="vendor")


# ── Document ──────────────────────────────────────────────────────────────────

class Document(Base):
    """One row per uploaded document within a vendor / M&A run."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="application/octet-stream")
    gcs_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    gemini_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship("Chunk", back_populates="document")


# ── Chunk ─────────────────────────────────────────────────────────────────────

class Chunk(Base):
    """pgvector-indexed text chunk derived from a Document.

    The ``embedding`` column uses pgvector's ``Vector(768)`` type so similarity
    search can be performed with the ``<=>`` operator (cosine distance).
    Dimension 768 matches ``text-embedding-004`` and ``model2vec`` defaults.
    """

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Any] = mapped_column(Vector(768), nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped["Document"] = relationship("Document", back_populates="chunks")


# ── FindingRow ────────────────────────────────────────────────────────────────

class FindingRow(Base):
    """Persisted agent finding.

    Named ``FindingRow`` to avoid collision with the Pydantic ``Finding``
    class in ``orchestra_tprm.schemas``.
    """

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    @classmethod
    def from_finding(cls, run_id: str, f: "Finding") -> "FindingRow":  # noqa: F821
        from orchestra_tprm.schemas import Finding as _Finding  # noqa: F401
        return cls(
            run_id=run_id,
            agent_name=f.agent,
            category=f.category,
            severity=f.severity,
            summary=f.summary,
            payload=f.raw,
            citations=[c.model_dump() for c in f.evidence],
        )


# ── AuditEvent ────────────────────────────────────────────────────────────────

class AuditEvent(Base):
    """Append-only compliance / observability event log.

    One row per significant event (run started, agent completed, finding
    persisted, verdict issued, error raised, etc.).
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
