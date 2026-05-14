"""Initial TPRM schema — vendors, documents, chunks, findings, audit_events.

Revision ID: 0001
Revises:
Create Date: 2026-05-15

DO NOT RUN until Cloud SQL instance is provisioned and pgvector extension
has been enabled manually (see infra/cloudsql_bootstrap.sh).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Revision identifiers (used by Alembic).
# ---------------------------------------------------------------------------
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── pgvector extension ────────────────────────────────────────────────────
    # Requires the Cloud SQL instance to have been bootstrapped first.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── vendors ───────────────────────────────────────────────────────────────
    op.create_table(
        "vendors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendors_name", "vendors", ["name"])

    # ── documents ─────────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vendor_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("file_name", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False, server_default="application/octet-stream"),
        sa.Column("gcs_uri", sa.String(1024), nullable=True),
        sa.Column("gemini_file_id", sa.String(256), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_vendor_id", "documents", ["vendor_id"])
    op.create_index("ix_documents_run_id", "documents", ["run_id"])

    # ── chunks ────────────────────────────────────────────────────────────────
    # Uses pgvector VECTOR type for the embedding column (dim=768).
    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),  # overridden below via DDL
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("char_offset", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Alter embedding column to proper VECTOR(768) type (pgvector DDL not in sa types).
    op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(768) USING NULL")
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    # IVFFlat index for approximate nearest-neighbour search (created after data load).
    # op.execute(
    #     "CREATE INDEX ix_chunks_embedding_ivfflat "
    #     "ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    # )

    # ── findings ──────────────────────────────────────────────────────────────
    op.create_table(
        "findings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("agent_name", sa.String(128), nullable=False),
        sa.Column("category", sa.String(128), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_findings_run_id", "findings", ["run_id"])

    # ── audit_events ──────────────────────────────────────────────────────────
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("severity", sa.String(16), nullable=False, server_default="info"),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_run_id", "audit_events", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_run_id", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_findings_run_id", table_name="findings")
    op.drop_table("findings")

    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_table("chunks")

    op.drop_index("ix_documents_run_id", table_name="documents")
    op.drop_index("ix_documents_vendor_id", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_vendors_name", table_name="vendors")
    op.drop_table("vendors")

    op.execute("DROP EXTENSION IF EXISTS vector")
