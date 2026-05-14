"""Idempotently create the BigQuery dataset and tprm_findings table.

Usage
-----
    # Dry-run — prints the intended schema without any API calls:
    python scripts/tprm_bootstrap_bq.py --dry-run

    # Live — creates dataset + table (safe to run multiple times):
    python scripts/tprm_bootstrap_bq.py

Configuration is read from environment variables with sensible defaults:
    GOOGLE_CLOUD_PROJECT  — GCP project ID (required in live mode)
    BQ_DATASET            — dataset name (default: tprm_audit)
    BQ_TABLE              — table name   (default: tprm_findings)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Config (mirrors the pydantic-settings pattern used elsewhere in orchestra_tprm)
# ---------------------------------------------------------------------------

@dataclass
class _BQBootstrapSettings:
    """Lightweight settings resolved from environment variables.

    Mirrors the pydantic-settings pattern used in the orchestra_tprm package
    but avoids importing settings.py (which may require optional deps) so this
    script stays self-contained and importable in any environment.
    """

    google_cloud_project: str = field(
        default_factory=lambda: os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    )
    bq_dataset: str = field(
        default_factory=lambda: os.environ.get("BQ_DATASET", "tprm_audit")
    )
    bq_table: str = field(
        default_factory=lambda: os.environ.get("BQ_TABLE", "tprm_findings")
    )


# ---------------------------------------------------------------------------
# BQ schema — mirrors Finding / FindingRow fields from schemas.py exactly
#
# Finding fields (src/orchestra_tprm/schemas.py):
#   agent       : str
#   category    : str
#   severity    : SeverityLiteral  ("low" | "medium" | "high" | "critical")
#   evidence    : list[Citation]   → serialised as JSON
#   summary     : str
#   raw         : dict[str, Any]   → serialised as JSON
#
# Added by BigQueryAdapter._findings_to_rows (the "FindingRow" envelope):
#   run_id      : str
#   run_date    : date             → stored as DATE
#   ingested_at : datetime         → stored as TIMESTAMP
# ---------------------------------------------------------------------------

_SCHEMA_SPEC: list[dict[str, Any]] = [
    {"name": "run_id",      "type": "STRING",    "mode": "REQUIRED"},
    {"name": "run_date",    "type": "DATE",      "mode": "REQUIRED"},
    {"name": "ingested_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    {"name": "agent",       "type": "STRING",    "mode": "REQUIRED"},
    {"name": "category",    "type": "STRING",    "mode": "REQUIRED"},
    {"name": "severity",    "type": "STRING",    "mode": "REQUIRED"},
    {"name": "summary",     "type": "STRING",    "mode": "REQUIRED"},
    {"name": "evidence",    "type": "JSON",      "mode": "NULLABLE"},
    {"name": "raw",         "type": "JSON",      "mode": "NULLABLE"},
]


def _build_schema(bq: Any) -> list[Any]:
    """Convert _SCHEMA_SPEC dicts to bigquery.SchemaField objects."""
    return [
        bq.SchemaField(f["name"], f["type"], mode=f["mode"])
        for f in _SCHEMA_SPEC
    ]


# ---------------------------------------------------------------------------
# Dry-run printer
# ---------------------------------------------------------------------------

def _print_dry_run(cfg: _BQBootstrapSettings) -> None:
    print("=== DRY RUN — no API calls made ===\n")
    print(f"Project : {cfg.google_cloud_project or '(not set — GOOGLE_CLOUD_PROJECT)'}")
    print(f"Dataset : {cfg.bq_dataset}")
    print(f"Table   : {cfg.bq_table}")
    print(f"\nFull ref: {cfg.google_cloud_project}.{cfg.bq_dataset}.{cfg.bq_table}\n")
    print("Partitioning : DAY on run_date")
    print("Clustering   : severity, agent\n")
    print("Schema:")
    for f in _SCHEMA_SPEC:
        print(f"  {f['name']:<14} {f['type']:<12} {f['mode']}")
    print("\nNo changes made.")


# ---------------------------------------------------------------------------
# Live bootstrap
# ---------------------------------------------------------------------------

def bootstrap(cfg: _BQBootstrapSettings) -> None:
    """Create the BQ dataset and table if they do not already exist."""
    if not cfg.google_cloud_project:
        sys.exit("Error: GOOGLE_CLOUD_PROJECT environment variable is not set.")

    try:
        from google.cloud import bigquery  # type: ignore[import-not-found]
    except ImportError:
        sys.exit(
            "Error: google-cloud-bigquery is not installed.\n"
            "Install it with:  pip install google-cloud-bigquery"
        )

    client = bigquery.Client(project=cfg.google_cloud_project)

    # --- dataset -----------------------------------------------------------
    dataset_id = f"{cfg.google_cloud_project}.{cfg.bq_dataset}"
    dataset_ref = bigquery.Dataset(dataset_id)
    dataset_ref.location = "US"
    client.create_dataset(dataset_ref, exists_ok=True)
    print(f"Dataset ready : {dataset_id}")

    # --- table -------------------------------------------------------------
    schema = _build_schema(bigquery)
    table_id = f"{cfg.google_cloud_project}.{cfg.bq_dataset}.{cfg.bq_table}"
    table_ref = bigquery.Table(table_id, schema=schema)
    table_ref.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="run_date",
    )
    table_ref.clustering_fields = ["severity", "agent"]
    client.create_table(table_ref, exists_ok=True)
    print(f"Table ready   : {table_id}")
    print(f"\nReady: {table_id}")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Idempotently create the BigQuery dataset and tprm_findings table.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the intended schema without making any API calls.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    cfg = _BQBootstrapSettings()

    if args.dry_run:
        _print_dry_run(cfg)
    else:
        bootstrap(cfg)


if __name__ == "__main__":
    main()
