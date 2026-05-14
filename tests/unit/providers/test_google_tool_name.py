"""P-2: tool-result Message must carry the tool name so GoogleProvider
emits functionResponse.name = <real tool>, not "tool"."""
from __future__ import annotations

import pytest

from orchestra.core.types import Message, MessageRole, ToolCall
from orchestra.providers.google import _messages_to_gemini_format


def test_tool_message_preserves_name_for_gemini():
    messages = [
        Message(role=MessageRole.USER, content="search for cats"),
        Message(
            role=MessageRole.ASSISTANT,
            content="",
            tool_calls=[ToolCall(name="web_search", arguments={"q": "cats"})],
        ),
        Message(
            role=MessageRole.TOOL,
            content='{"hits": 3}',
            name="web_search",  # <-- this is what P-2 ensures the agent loop sets
            tool_call_id="call_abc",
        ),
    ]
    _, contents = _messages_to_gemini_format(messages)
    tool_part = contents[-1]["parts"][0]
    assert tool_part["functionResponse"]["name"] == "web_search"


@pytest.mark.asyncio
async def test_agent_loop_sets_name_on_tool_message():
    """Driving BaseAgent end-to-end: after a tool call, the TOOL-role Message
    appended to full_messages must have .name == tool_call.name (P-2).

    We intercept Message construction to capture the TOOL-role instance,
    because AgentResult.messages only surfaces the final ASSISTANT message.
    """
    import orchestra.core.agent as agent_mod
    from unittest.mock import patch
    from orchestra.core.agent import BaseAgent
    from orchestra.core.context import ExecutionContext
    from orchestra.core.types import LLMResponse
    from orchestra.testing import ScriptedLLM
    from orchestra.tools.base import tool

    captured: list[Message] = []
    _real_message = Message  # keep reference before patching

    def capturing_message(**kwargs):
        msg = _real_message(**kwargs)
        captured.append(msg)
        return msg

    @tool
    async def echo(payload: str) -> str:
        return f"got: {payload}"

    llm = ScriptedLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(name="echo", arguments={"payload": "hi"})],
            ),
            LLMResponse(content="done"),
        ]
    )
    agent = BaseAgent(name="t", tools=[echo], max_iterations=2)
    ctx = ExecutionContext(provider=llm)

    with patch.object(agent_mod, "Message", side_effect=capturing_message):
        await agent.run("go", ctx)

    tool_msgs = [m for m in captured if m.role == MessageRole.TOOL]
    assert tool_msgs, "P-2: no TOOL-role Message was appended during agent loop"
    assert tool_msgs[0].name == "echo", "P-2: tool-result Message lacks .name"
