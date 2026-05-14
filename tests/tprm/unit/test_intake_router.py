"""Unit tests for IntakeAgent (intake_node) and DocRouterAgent (router_node).

All tests are fully offline — no network I/O, no real Drive/Gemini calls.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from orchestra_tprm.agents.intake import intake_node
from orchestra_tprm.agents.router import router_node
from orchestra_tprm.modes.config import load_mode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manifest(tmp_path: Path, docs: list[dict[str, str]]) -> Path:
    """Write a minimal manifest.yaml and create stub files for each doc."""
    manifest_lines = ["subject_name: TestCorp", "docs:"]
    for doc in docs:
        manifest_lines.append(f"  - path: {doc['path']}")
        manifest_lines.append(f"    kind: {doc['kind']}")
        # Create the stub file so Path.resolve() has something to point at.
        (tmp_path / doc["path"]).write_bytes(b"%PDF-stub")
    (tmp_path / "manifest.yaml").write_text(
        "\n".join(manifest_lines) + "\n", encoding="utf-8"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# intake_node tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_intake_node_populates_packet_manifest(tmp_path: Path) -> None:
    """packet_manifest should have one entry per doc in manifest.yaml."""
    _make_manifest(tmp_path, [
        {"path": "contract.pdf", "kind": "contract"},
        {"path": "soc2.pdf", "kind": "security_attestation"},
    ])

    state: dict[str, Any] = {"packet_path": str(tmp_path)}
    result = await intake_node(state)

    manifest = result["packet_manifest"]
    assert len(manifest) == 2

    kinds = {entry["kind"] for entry in manifest}
    assert kinds == {"contract", "security_attestation"}

    for entry in manifest:
        assert "path" in entry
        assert "kind" in entry
        assert "file_uri" in entry


@pytest.mark.asyncio
async def test_intake_node_uses_local_file_uri(tmp_path: Path) -> None:
    """In local mode, every file_uri must start with ``local://``."""
    _make_manifest(tmp_path, [{"path": "annual_report.pdf", "kind": "annual_report"}])

    state: dict[str, Any] = {"packet_path": str(tmp_path)}
    result = await intake_node(state)

    for entry in result["packet_manifest"]:
        assert entry["file_uri"].startswith("local://"), (
            f"Expected local:// URI, got: {entry['file_uri']}"
        )

    # file_uris shorthand dict should also use local:// scheme
    for uri in result["file_uris"].values():
        assert uri.startswith("local://")


@pytest.mark.asyncio
async def test_intake_node_file_uris_keyed_by_kind(tmp_path: Path) -> None:
    """file_uris dict should be keyed by kind."""
    _make_manifest(tmp_path, [
        {"path": "contract.pdf", "kind": "contract"},
        {"path": "soc2.pdf", "kind": "security_attestation"},
    ])

    state: dict[str, Any] = {"packet_path": str(tmp_path)}
    result = await intake_node(state)

    assert "contract" in result["file_uris"]
    assert "security_attestation" in result["file_uris"]


@pytest.mark.asyncio
async def test_intake_node_subject_name_from_state(tmp_path: Path) -> None:
    """subject_name pre-set in state takes precedence over manifest."""
    _make_manifest(tmp_path, [{"path": "doc.pdf", "kind": "unknown"}])

    state: dict[str, Any] = {
        "packet_path": str(tmp_path),
        "subject_name": "OverrideCorp",
    }
    result = await intake_node(state)

    assert result["subject_name"] == "OverrideCorp"


@pytest.mark.asyncio
async def test_intake_node_subject_name_from_manifest(tmp_path: Path) -> None:
    """When state has no subject_name, fall back to manifest value."""
    _make_manifest(tmp_path, [{"path": "doc.pdf", "kind": "unknown"}])

    state: dict[str, Any] = {"packet_path": str(tmp_path)}
    result = await intake_node(state)

    assert result["subject_name"] == "TestCorp"


@pytest.mark.asyncio
async def test_intake_node_missing_manifest_raises(tmp_path: Path) -> None:
    """Missing manifest.yaml should raise FileNotFoundError."""
    state: dict[str, Any] = {"packet_path": str(tmp_path)}

    with pytest.raises(FileNotFoundError):
        await intake_node(state)


# ---------------------------------------------------------------------------
# router_node tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_node_routes_contract_to_legal() -> None:
    """A ``contract`` doc must be routed to the ``legal`` specialist."""
    cfg = load_mode("vendor")
    state: dict[str, Any] = {
        "packet_manifest": [
            {
                "path": "/fake/contract.pdf",
                "kind": "contract",
                "file_uri": "local:///fake/contract.pdf",
            }
        ]
    }

    result = await router_node(state, cfg)

    assert "legal" in result["routing"]
    assert len(result["routing"]["legal"]) == 1
    assert result["routing"]["legal"][0] == "local:///fake/contract.pdf"


@pytest.mark.asyncio
async def test_router_node_skips_inactive_specialists() -> None:
    """Vendor mode has ``financial=None``; ``financial`` must not appear in routing."""
    cfg = load_mode("vendor")
    # financial_statement routes to both financial and legal, but financial is null
    state: dict[str, Any] = {
        "packet_manifest": [
            {
                "path": "/fake/fin.pdf",
                "kind": "financial_statement",
                "file_uri": "local:///fake/fin.pdf",
            }
        ]
    }

    result = await router_node(state, cfg)

    assert "financial" not in result["routing"], (
        "financial specialist is null in vendor mode and must be excluded from routing"
    )
    # legal should still receive it
    assert "legal" in result["routing"]
    assert len(result["routing"]["legal"]) == 1


@pytest.mark.asyncio
async def test_router_node_empty_manifest_returns_empty_routing() -> None:
    """Empty packet_manifest should produce all-empty routing lists."""
    cfg = load_mode("vendor")
    state: dict[str, Any] = {"packet_manifest": []}

    result = await router_node(state, cfg)

    routing = result["routing"]
    # Every active specialist key should be present but with an empty list
    assert routing, "routing dict should not be missing entirely"
    for spec, uris in routing.items():
        assert uris == [], f"Expected empty list for {spec}, got {uris}"


@pytest.mark.asyncio
async def test_router_node_active_specialists_all_have_keys() -> None:
    """All active specialists get a key in routing even if no docs are routed."""
    cfg = load_mode("vendor")
    state: dict[str, Any] = {"packet_manifest": []}

    result = await router_node(state, cfg)

    # Vendor active: legal, security, code, external  (financial=None → absent)
    routing = result["routing"]
    assert "legal" in routing
    assert "security" in routing
    assert "code" in routing
    assert "external" in routing
    assert "financial" not in routing


@pytest.mark.asyncio
async def test_router_node_security_attestation_routes_to_security() -> None:
    """``security_attestation`` kind must be routed to the ``security`` specialist."""
    cfg = load_mode("vendor")
    uri = "local:///fake/soc2.pdf"
    state: dict[str, Any] = {
        "packet_manifest": [
            {"path": "/fake/soc2.pdf", "kind": "security_attestation", "file_uri": uri}
        ]
    }

    result = await router_node(state, cfg)

    assert uri in result["routing"]["security"]


@pytest.mark.asyncio
async def test_router_node_annual_report_multi_specialist() -> None:
    """``annual_report`` should fan out to legal, financial (if active), and security."""
    cfg = load_mode("ma")  # M&A mode has all specialists active
    uri = "local:///fake/annual.pdf"
    state: dict[str, Any] = {
        "packet_manifest": [
            {"path": "/fake/annual.pdf", "kind": "annual_report", "file_uri": uri}
        ]
    }

    result = await router_node(state, cfg)

    assert uri in result["routing"]["legal"]
    assert uri in result["routing"]["financial"]
    assert uri in result["routing"]["security"]
