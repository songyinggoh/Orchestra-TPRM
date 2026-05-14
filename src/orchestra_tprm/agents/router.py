"""DocRouterAgent — mode-aware document routing node.

Classifies each document in ``packet_manifest`` by ``kind`` and assigns
its ``file_uri`` to every active specialist that cares about that kind.

"Active" means the specialist has a non-``None`` model in ``ModeConfig.specialists``.
Vendor mode disables ``financial``; M&A mode enables all.

The node is a plain async callable (not a ``BaseTPRMAgent`` subclass) because
it emits no ``Finding`` objects.  Wire it into the graph as a closure so
``cfg`` is injected at graph-build time::

    graph.add_node("router", lambda state: router_node(state, mode_cfg))

Returns:
    ``{"routing": {specialist_name: [file_uri, ...], ...}}``
"""
from __future__ import annotations

from typing import Any

from orchestra_tprm.modes.config import ModeConfig

# Which doc kinds each specialist is interested in by default.
# Keys are ``kind`` values from manifest.yaml; values are specialist names
# that match ``SpecialistModels`` field names.
_KIND_TO_SPECIALISTS: dict[str, list[str]] = {
    "contract": ["legal"],
    "security_attestation": ["security"],
    "financial_statement": ["financial", "legal"],
    "source_code": ["code"],
    "investor_deck": ["financial"],
    "annual_report": ["legal", "financial", "security"],
    "unknown": ["legal", "security"],
}


async def router_node(state: dict[str, Any], cfg: ModeConfig) -> dict[str, Any]:
    """Classify docs and build per-specialist file-URI lists.

    Args:
        state: Workflow state dict.  Must contain ``packet_manifest`` (list of
               ``{path, kind, file_uri}`` dicts).
        cfg:   ModeConfig for the current run.  Determines which specialists
               are active based on non-``None`` model assignments.

    Returns:
        ``{"routing": {specialist: [file_uri, ...]}}`` where each specialist
        key is present only for active specialists.
    """
    packet_manifest: list[dict[str, Any]] = state.get("packet_manifest", [])

    # Build the set of active (enabled) specialists from the mode config.
    active: set[str] = {
        k for k, v in cfg.specialists.model_dump().items() if v is not None
    }

    # Initialise routing dict so every active specialist has an entry even
    # if no docs are routed to them (avoids KeyError in downstream nodes).
    routing: dict[str, list[str]] = {s: [] for s in active}

    for doc in packet_manifest:
        kind: str = doc.get("kind", "unknown")
        file_uri: str = doc.get("file_uri", "")
        target_specialists = _KIND_TO_SPECIALISTS.get(kind, ["legal", "security"])
        for spec in target_specialists:
            if spec in active:
                routing[spec].append(file_uri)

    return {"routing": routing}
