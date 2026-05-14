"""Unit tests for the FastAPI server skeleton."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orchestra_tprm.server.app import app

client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_run_endpoint_accepts_vendor_mode() -> None:
    response = client.post(
        "/run",
        json={"mode": "vendor", "subject_name": "Acme", "packet_path": "/tmp/acme"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "run_id" in body
    assert body["status"] == "accepted"
    assert len(body["run_id"]) > 0


def test_run_endpoint_accepts_ma_mode() -> None:
    response = client.post(
        "/run",
        json={"mode": "ma", "subject_name": "TargetCorp", "packet_path": "/tmp/target"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "run_id" in body
    assert body["status"] == "accepted"


def test_run_endpoint_rejects_invalid_mode() -> None:
    response = client.post(
        "/run",
        json={"mode": "invalid", "subject_name": "X", "packet_path": "/tmp/x"},
    )
    assert response.status_code == 422  # Pydantic validation error


def test_events_endpoint_returns_sse_stub() -> None:
    response = client.get("/events/test-run-123")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
