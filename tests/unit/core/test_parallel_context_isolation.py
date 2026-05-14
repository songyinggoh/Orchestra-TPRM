"""P-3: parallel branches must not clobber each other's node_id, turn_number,
or loop_counters."""
from __future__ import annotations

import asyncio

import pytest

from orchestra.core.context import ExecutionContext
from orchestra.core.graph import WorkflowGraph
from orchestra.core.runner import run
from orchestra.core.state import WorkflowState, merge_dict
from orchestra.core.types import END
from typing import Annotated


class S(WorkflowState):
    seen: Annotated[dict[str, str], merge_dict] = {}


def make_recorder(name: str):
    async def _node(state: dict):
        # Sleep so the branches genuinely overlap
        await asyncio.sleep(0.05)
        # The injected ExecutionContext is in the state under "__ctx__" (test hook)
        ctx: ExecutionContext = state.get("__ctx__")
        return {"seen": {name: ctx.node_id if ctx else "<missing>"}}
    return _node


@pytest.mark.asyncio
async def test_parallel_branches_have_distinct_node_ids(monkeypatch):
    # Inject ctx into state so the recorder can see what context.node_id is
    from orchestra.core import compiled as compiled_mod

    real_exec_node = compiled_mod.CompiledGraph._execute_node

    async def patched_exec_node(self, node_id, node, state_dict, context):
        state_dict = dict(state_dict)
        state_dict["__ctx__"] = context
        return await real_exec_node(self, node_id, node, state_dict, context)

    monkeypatch.setattr(compiled_mod.CompiledGraph, "_execute_node", patched_exec_node)

    graph = WorkflowGraph(state_schema=S)
    graph.add_node("dispatch", lambda s: {})
    graph.add_node("a", make_recorder("a"))
    graph.add_node("b", make_recorder("b"))
    graph.add_node("c", make_recorder("c"))
    graph.add_node("join", lambda s: {})
    graph.set_entry_point("dispatch")
    graph.add_parallel("dispatch", ["a", "b", "c"], join_node="join")
    graph.add_edge("join", END)

    result = await run(graph, input={}, persist=False)
    assert result.state["seen"] == {"a": "a", "b": "b", "c": "c"}, (
        "P-3: parallel branches saw clobbered node_id values"
    )


def test_clone_for_branch_is_independent():
    parent = ExecutionContext(node_id="parent", turn_number=5)
    parent.loop_counters["x"] = 7
    child = parent.clone_for_branch(node_id="child")
    child.loop_counters["x"] = 99
    child.turn_number = 0
    assert parent.node_id == "parent"
    assert parent.turn_number == 5
    assert parent.loop_counters["x"] == 7
    assert child.node_id == "child"
