"""Replay LLM Provider for side-effect safe time-travel.

Wraps historical events and returns recorded LLM responses instead of
calling real APIs during replay/forked phases.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from orchestra.core.types import LLMResponse, Message, TokenUsage, ToolCall
from orchestra.storage.events import AnyEvent, LLMCalled

_event_adapter: TypeAdapter[AnyEvent] = TypeAdapter(AnyEvent)


def hash_messages(messages: list[Message]) -> str:
    """Stable SHA-256 hex of a messages list.

    Used to bind recorded responses to their originating prompt so that
    parallel agents replay correctly regardless of completion order.
    """
    h = hashlib.sha256()
    for m in messages:
        role = getattr(m.role, "value", str(m.role))
        h.update(role.encode("utf-8"))
        h.update(b"\x00")
        h.update((m.content or "").encode("utf-8"))
        h.update(b"\x00")
        atts = getattr(m, "attachments", None) or []
        for a in atts:
            h.update(json.dumps(a, sort_keys=True, default=str).encode("utf-8"))
            h.update(b"\x00")
    return h.hexdigest()


class ReplayProvider:
    """LLM Provider that 'plays back' recorded responses from history.

    Replay lookup order:
    1. Match by ``prompt_hash`` (stable under parallel fan-out reordering).
    2. Fall back to sequential pointer for legacy recordings without hashes.
    """

    @classmethod
    def from_jsonl(cls, path: str) -> "ReplayProvider":
        """Load a ReplayProvider from a JSONL recording file."""
        events: list[LLMCalled] = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            try:
                event = _event_adapter.validate_python(data)
                if isinstance(event, LLMCalled):
                    events.append(event)
            except Exception:
                pass
        return cls(events)

    def __init__(self, historical_events: Iterable[Any]) -> None:
        self._llm_calls = [e for e in historical_events if isinstance(e, LLMCalled)]
        self._ptr = 0
        # Build hash→queue index. Same hash may appear multiple times (e.g., a
        # specialist retried under safety filter); FIFO preserves call order.
        self._by_hash: dict[str, list[int]] = {}
        for i, call in enumerate(self._llm_calls):
            if call.prompt_hash:
                self._by_hash.setdefault(call.prompt_hash, []).append(i)

    async def complete(
        self,
        messages: list[Message],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Return the recorded response matching the prompt hash; else fall back to sequential."""
        h = hash_messages(messages)
        call: LLMCalled | None = None
        if h in self._by_hash and self._by_hash[h]:
            idx = self._by_hash[h].pop(0)
            call = self._llm_calls[idx]
        elif self._ptr < len(self._llm_calls):
            call = self._llm_calls[self._ptr]
            self._ptr += 1
        else:
            raise RuntimeError(
                "ReplayProvider exhausted historical LLM calls. "
                "The workflow has diverged from history."
            )

        tool_calls = []
        if call.tool_calls:
            for tc_dict in call.tool_calls:
                tool_calls.append(ToolCall.model_validate(tc_dict))

        return LLMResponse(
            content=call.content or "",
            tool_calls=tool_calls,
            usage=TokenUsage(
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                total_tokens=call.input_tokens + call.output_tokens,
                estimated_cost_usd=call.cost_usd,
            ),
            model=call.model,
        )
