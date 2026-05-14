"""SQLAlchemy mapped classes for TPRM durable state."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class FindingRow(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    agent_name: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    @classmethod
    def from_finding(cls, run_id: str, f: "Finding") -> "FindingRow":
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
