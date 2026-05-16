"""BigQueryAdapter — post-run ``bq load`` shipper.

Pipeline (locked decision)
--------------------------
1. During the run, PolicyAgent / agents write ``audit_events`` rows to
   Postgres (Cloud SQL pgvector instance).
2. At run-end (called by CLI/coordinator),
   :meth:`BigQueryAdapter.ship_audit_events_to_bq` reads the run's rows from
   Postgres, serialises them, and runs ONE ``load_table_from_json`` job into
   BQ (``tprm_audit.tprm_findings``).

No streaming inserts. No Pub/Sub. Pub/Sub is on the production roadmap.

The legacy :class:`FakeBigQueryAdapter` (with ``insert_row``/``insert_rows``)
is preserved unmodified for backwards-compatibility with earlier unit tests.

Live Cloud SQL Postgres is NOT YET PROVISIONED at the time of this commit —
the integration path is intentionally untested at the live layer. Unit tests
mock both the Postgres session factory and ``google.cloud.bigquery.Client``.
"""
from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any

from orchestra_tprm.schemas import Finding

# Env defaults — overridable per call but match the bootstrap script (Task 18).
_DEFAULT_DATASET = os.environ.get("BQ_DATASET", "tprm_audit")
_DEFAULT_TABLE = os.environ.get("BQ_TABLE", "tprm_findings")


def _import_bigquery() -> Any:
    """Lazily import ``google.cloud.bigquery``.

    Indirection lets unit tests patch this single seam instead of monkey-
    patching the google namespace.
    """
    from google.cloud import bigquery  # type: ignore[import-not-found]

    return bigquery


def _findings_to_rows(
    run_id: str,
    findings: list[Finding],
    *,
    mode: str = "",
    subject: str = "",
) -> list[dict[str, Any]]:
    """Serialise ``Finding`` objects to BQ-ready row dicts.

    ``evidence`` and ``raw`` are JSON-encoded strings — BQ ``JSON`` columns
    accept stringified JSON via ``load_table_from_json``.
    """
    if not findings:
        return []
    now = datetime.now(UTC)
    out: list[dict[str, Any]] = []
    for f in findings:
        out.append(
            {
                "run_id": run_id,
                "run_date": now.date().isoformat(),
                "mode": mode,
                "subject": subject,
                "agent": f.agent,
                "category": f.category,
                "severity": f.severity,
                "summary": f.summary,
                "evidence": json.dumps([c.model_dump() for c in f.evidence]),
                "raw": json.dumps(f.raw),
                "created_at": now.isoformat(),
            }
        )
    return out


# Type alias: an async-context-manager factory yielding an SQLAlchemy session.
SessionFactory = Callable[[], AbstractAsyncContextManager[Any]]


def _default_session_factory() -> AbstractAsyncContextManager[Any]:
    """Resolve the project-wide session factory lazily.

    Imported on first use so the module remains importable before the
    data-layer module (``orchestra_tprm.storage.db``) lands. Tests inject
    their own factory and never trigger this path.
    """
    from orchestra_tprm.storage.db import session  # type: ignore[import-not-found]

    return session()


class BigQueryAdapter:
    """Real BigQuery adapter — thin wrapper around a post-run batch load.

    Two entry points
    ----------------
    * :meth:`ship_audit_events_to_bq` — primary path: reads ``audit_events``
      rows from Postgres for a given ``run_id`` and batch-loads them.
    * :meth:`append_findings` — convenience path that serialises an in-memory
      ``list[Finding]`` and runs the same single ``load_table_from_json`` job.
      Used by the coordinator when the Postgres write path is bypassed
      (e.g. local smoke runs without a live DB).
    """

    def __init__(self, project: str | None = None) -> None:
        self._project = project
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            bq = _import_bigquery()
            self._client = bq.Client(project=self._project)
        return self._client

    async def _load_rows(
        self, dataset: str, table: str, rows: list[dict[str, Any]]
    ) -> int:
        """Run a single ``load_table_from_json`` job and block until done."""
        if not rows:
            return 0

        def _do() -> int:
            bq = _import_bigquery()
            client = self._get_client()
            table_ref = client.dataset(dataset).table(table)
            job_config = bq.LoadJobConfig(
                write_disposition=bq.WriteDisposition.WRITE_APPEND,
            )
            job = client.load_table_from_json(rows, table_ref, job_config=job_config)
            job.result()  # blocks until the load completes
            return len(rows)

        return await asyncio.to_thread(_do)

    async def ship_audit_events_to_bq(
        self,
        dataset: str | None = None,
        table: str | None = None,
        run_id: str = "",
        *,
        session_factory: SessionFactory | None = None,
    ) -> int:
        """Read audit_events for ``run_id`` from Postgres, batch-load to BQ.

        Called ONCE per run at end-of-run. Returns the number of rows loaded.
        ``session_factory`` is injected by tests; production callers use the
        default (resolved lazily from ``orchestra_tprm.storage.db.session``).
        """
        ds = dataset or _DEFAULT_DATASET
        tb = table or _DEFAULT_TABLE
        from sqlalchemy import text as _text  # type: ignore[import-not-found]

        ctx: AbstractAsyncContextManager[Any]
        ctx = session_factory() if session_factory is not None else _default_session_factory()

        async with ctx as s:
            result = await s.execute(
                _text(
                    "SELECT run_id, ts, event_type, payload "
                    "FROM audit_events WHERE run_id = :run_id"
                ),
                {"run_id": run_id},
            )
            rows = [dict(r._mapping) for r in result]

        return await self._load_rows(ds, tb, rows)

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
        """Convenience: serialise findings → single load job. Returns row count."""
        rows = _findings_to_rows(run_id, findings, mode=mode, subject=subject)
        return await self._load_rows(dataset, table, rows)


class FakeBigQueryAdapter:
    def __init__(self) -> None:
        self._tables: dict[tuple[str, str], list[dict]] = {}

    def insert_row(self, dataset: str, table: str, row_dict: dict) -> None:
        self._tables.setdefault((dataset, table), []).append(dict(row_dict))

    def insert_rows(self, dataset: str, table: str, rows: list[dict]) -> None:
        store = self._tables.setdefault((dataset, table), [])
        store.extend(dict(r) for r in rows)

