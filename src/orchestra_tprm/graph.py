"""Build a per-mode CompiledGraph. Day 1: stub nodes that return empty
findings. Real specialist wiring lands in Day 2-3."""
from __future__ import annotations

from typing import Any

from orchestra.core.graph import WorkflowGraph
from orchestra.core.types import END

from orchestra_tprm.modes.config import ModeConfig
from orchestra_tprm.schemas import TPRMState


async def _stub_intake(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "subject_name": state.get("subject_name") or "Acme Cloud Analytics",
        "packet_manifest": [],
    }


async def _stub_join(state: dict[str, Any]) -> dict[str, Any]:
    return {"findings": []}


async def _stub_coordinator(state: dict[str, Any]) -> dict[str, Any]:
    return {"verdict_local_path": "/tmp/stub-verdict"}


def build_graph(mode: ModeConfig) -> Any:
    g = WorkflowGraph(state_schema=TPRMState)
    g.add_node("intake", _stub_intake, output_key="packet_manifest")
    g.add_node("coordinator", _stub_coordinator, output_key="verdict_local_path")
    g.add_node("join", _stub_join, output_key="findings")
    g.set_entry_point("intake")
    g.add_edge("intake", "coordinator")
    g.add_edge("coordinator", "join")
    g.add_edge("join", END)
    return g.compile()
