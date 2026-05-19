"""Tests for GoogleProvider.

Uses httpx mock transport to avoid real API calls.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from orchestra.core.errors import (
    AuthenticationError,
    ContextWindowError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
)
from orchestra.core.types import (
    LLMResponse,
    Message,
    MessageRole,
    ModelCost,
)
from orchestra.providers.google import GoogleProvider, _messages_to_gemini_format

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(role: MessageRole, content: str) -> Message:
    return Message(role=role, content=content)


def _user(content: str) -> Message:
    return _make_message(MessageRole.USER, content)


def _system(content: str) -> Message:
    return _make_message(MessageRole.SYSTEM, content)


def _assistant(content: str) -> Message:
    return _make_message(MessageRole.ASSISTANT, content)


def _make_mock_transport(
    status_code: int,
    body: Any,
    *,
    content_type: str = "application/json",
) -> httpx.MockTransport:
    """Create a mock HTTPX transport returning a fixed response."""
    content = json.dumps(body).encode() if isinstance(body, (dict, list)) else str(body).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            content=content,
            headers={"content-type": content_type},
        )

    return httpx.MockTransport(handler)


def _make_sse_transport(lines: list[str]) -> httpx.MockTransport:
    """Create a mock transport returning SSE-formatted lines."""
    content = "\n".join(lines).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=content,
            headers={"content-type": "text/event-stream"},
        )

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Google Provider Tests
# ---------------------------------------------------------------------------


class TestGoogleProvider:
    """8 tests for GoogleProvider."""

    def _make_provider(self, transport: httpx.MockTransport) -> GoogleProvider:
        provider = GoogleProvider(api_key="test-key")
        provider._client = httpx.AsyncClient(
            base_url="https://generativelanguage.googleapis.com",
            transport=transport,
        )
        return provider

    def _gemini_response(
        self,
        text: str = "Hello!",
        finish_reason: str = "STOP",
        input_tokens: int = 10,
        output_tokens: int = 5,
        function_calls: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        parts: list[dict[str, Any]] = []
        if text:
            parts.append({"text": text})
        if function_calls:
            for fc in function_calls:
                parts.append({"functionCall": fc})

        return {
            "candidates": [
                {
                    "content": {"role": "model", "parts": parts},
                    "finishReason": finish_reason,
                }
            ],
            "usageMetadata": {
                "promptTokenCount": input_tokens,
                "candidatesTokenCount": output_tokens,
                "totalTokenCount": input_tokens + output_tokens,
            },
        }

    # --- Test 1: Complete (chat, no tools) -> LLMResponse ---

    @pytest.mark.asyncio
    async def test_complete_returns_llm_response(self) -> None:
        transport = _make_mock_transport(200, self._gemini_response("Hello from Gemini!"))
        provider = self._make_provider(transport)

        result = await provider.complete([_user("Hi")])

        assert isinstance(result, LLMResponse)
        assert result.content == "Hello from Gemini!"
        assert result.finish_reason == "stop"
        assert result.tool_calls == []

    # --- Test 2: Complete with tool calling -> LLMResponse with tool_calls ---

    @pytest.mark.asyncio
    async def test_complete_with_tool_calls(self) -> None:
        response_body = self._gemini_response(
            text="",
            finish_reason="FUNCTION_CALL",
            function_calls=[{"name": "get_weather", "args": {"location": "Paris"}}],
        )
        transport = _make_mock_transport(200, response_body)
        provider = self._make_provider(transport)

        result = await provider.complete(
            [_user("What's the weather in Paris?")],
            tools=[
                {
                    "function": {
                        "name": "get_weather",
                        "description": "Get weather",
                        "parameters": {
                            "type": "object",
                            "properties": {"location": {"type": "string"}},
                        },
                    }
                }
            ],
        )

        assert isinstance(result, LLMResponse)
        assert result.finish_reason == "tool_calls"
        assert len(result.tool_calls) == 1
        tc = result.tool_calls[0]
        assert tc.name == "get_weather"
        assert tc.arguments == {"location": "Paris"}

    # --- Test 3: Streaming -> yields StreamChunks ---

    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self) -> None:
        chunk1 = {"candidates": [{"content": {"parts": [{"text": "Hello"}]}, "finishReason": ""}]}
        chunk2 = {
            "candidates": [{"content": {"parts": [{"text": " world"}]}, "finishReason": "STOP"}]
        }
        sse_lines = [
            f"data: {json.dumps(chunk1)}",
            f"data: {json.dumps(chunk2)}",
        ]
        transport = _make_sse_transport(sse_lines)
        provider = self._make_provider(transport)

        chunks = []
        async for chunk in provider.stream([_user("Hi")]):
            chunks.append(chunk)

        texts = [c.content for c in chunks if c.content]
        assert "Hello" in texts
        assert " world" in texts

    # --- Test 4: Error: invalid API key -> AuthenticationError ---

    @pytest.mark.asyncio
    async def test_error_invalid_api_key_raises_auth_error(self) -> None:
        error_body = {"error": {"code": 403, "message": "API key not valid."}}
        transport = _make_mock_transport(403, error_body)
        provider = self._make_provider(transport)

        with pytest.raises(AuthenticationError):
            await provider.complete([_user("Hello")])

    # --- Test 5: Error: rate limit -> RateLimitError ---

    @pytest.mark.asyncio
    async def test_error_rate_limit_raises_rate_limit_error(self) -> None:
        error_body = {"error": {"code": 429, "message": "Quota exceeded."}}
        transport = _make_mock_transport(429, error_body)
        # Override retries to 0 to avoid slow test
        provider = GoogleProvider(api_key="test", max_retries=0)
        provider._client = httpx.AsyncClient(
            base_url="https://generativelanguage.googleapis.com",
            transport=transport,
        )

        with pytest.raises(RateLimitError):
            await provider.complete([_user("Hello")])

    # --- Test 6: Error: context window exceeded -> ContextWindowError ---

    @pytest.mark.asyncio
    async def test_error_context_window_raises_context_window_error(self) -> None:
        error_body = {
            "error": {
                "code": 400,
                "message": "Request payload size exceeds the limit: context length exceeded.",
            }
        }
        transport = _make_mock_transport(400, error_body)
        provider = self._make_provider(transport)

        with pytest.raises(ContextWindowError):
            await provider.complete([_user("A" * 100_000)])

    # --- Test 7: Token counting -> int ---

    def test_count_tokens_returns_int(self) -> None:
        provider = GoogleProvider(api_key="test")
        messages = [_system("You are helpful."), _user("Hello, world!")]
        count = provider.count_tokens(messages)
        assert isinstance(count, int)
        assert count > 0

    # --- Test 8: Model cost lookup -> ModelCost ---

    def test_get_model_cost_returns_model_cost(self) -> None:
        provider = GoogleProvider(api_key="test")

        cost = provider.get_model_cost("gemini-2.0-flash")
        assert isinstance(cost, ModelCost)
        assert cost.input_cost_per_1k == 0.0001
        assert cost.output_cost_per_1k == 0.0004

        # Unknown model returns (0.0, 0.0)
        cost_unknown = provider.get_model_cost("gemini-unknown")
        assert cost_unknown.input_cost_per_1k == 0.0
        assert cost_unknown.output_cost_per_1k == 0.0


# ---------------------------------------------------------------------------
# Shared: message format conversion
# ---------------------------------------------------------------------------


class TestGeminiMessageConversion:
    """Extra coverage for message format conversion edge cases."""

    def test_system_message_extracted(self) -> None:
        messages = [_system("Be helpful"), _user("Hello")]
        system, contents = _messages_to_gemini_format(messages)
        assert system == "Be helpful"
        assert len(contents) == 1
        assert contents[0]["role"] == "user"

    def test_assistant_becomes_model_role(self) -> None:
        messages = [_user("Hi"), _assistant("Hello back")]
        _, contents = _messages_to_gemini_format(messages)
        assert contents[1]["role"] == "model"
        assert contents[1]["parts"][0]["text"] == "Hello back"
