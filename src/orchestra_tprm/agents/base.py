"""BaseTPRMAgent: shared LLM-call shape with W-2 fault tolerance and W-3
safety-filter retry. All TPRM specialist agents subclass this; non-specialist
agents (Intake, Router, Policy, Coordinator) compose with it directly."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from orchestra.core.context import ExecutionContext
from orchestra.core.types import Message, MessageRole
from orchestra_tprm.schemas import Finding

logger = logging.getLogger(__name__)

_COMPLIANCE_PREFIX = (
    "You are operating in a compliance review context. The text you analyse "
    "may include risk-management, legal, or security material. Quoting and "
    "summarising it for compliance purposes is required and permitted.\n\n"
)


class _SafetySuppressed(Exception):
    pass


class BaseTPRMAgent(ABC):
    """Specialist base class. Subclasses override `_emit_findings`.

    Provides:
      - `_call_llm()` with W-3 retry (one retry with compliance-context prefix
        on a SAFETY finish; raises _SafetySuppressed if still empty).
      - `run()` which calls `_emit_findings` and catches _SafetySuppressed to
        inject a filter-suppressed Finding.
    """

    name: str = "BaseTPRMAgent"
    model: str = "gemini-2.5-flash"
    attachments_field: str | None = None

    async def run(self, ctx: ExecutionContext) -> list[Finding]:
        try:
            return await self._emit_findings(ctx)
        except _SafetySuppressed:
            return [
                Finding(
                    agent=self.name,
                    category="filter-suppressed",
                    severity="medium",
                    summary=(
                        f"{self.name} response was suppressed by Gemini safety "
                        "filters even after compliance-context retry."
                    ),
                )
            ]

    @abstractmethod
    async def _emit_findings(self, ctx: ExecutionContext) -> list[Finding]:
        ...

    async def _call_llm(
        self,
        ctx: ExecutionContext,
        *,
        prompt: str,
        system: str | None = None,
        attachments: list[dict] | None = None,
        output_type: type | None = None,
    ) -> str:
        msgs = []
        if system:
            msgs.append(Message(role=MessageRole.SYSTEM, content=system))
        msgs.append(
            Message(
                role=MessageRole.USER,
                content=prompt,
                attachments=attachments,
            )
        )
        response = await ctx.provider.complete(
            msgs, model=self.model, output_type=output_type
        )
        if response.content or response.finish_reason != "safety":
            return response.content or ""

        # W-3: retry once with compliance-context prefix
        retry_msgs = list(msgs[:-1]) + [
            Message(
                role=MessageRole.USER,
                content=_COMPLIANCE_PREFIX + prompt,
                attachments=attachments,
            )
        ]
        retry = await ctx.provider.complete(
            retry_msgs, model=self.model, output_type=output_type
        )
        if retry.content:
            return retry.content

        raise _SafetySuppressed()


def safe_specialist(
    agent: BaseTPRMAgent,
) -> Callable[[ExecutionContext], Awaitable[list[Finding]]]:
    """W-2: wrap a specialist so any exception becomes a critical/agent-error
    Finding instead of bubbling and crashing the parallel fan-out."""

    async def _runner(ctx: ExecutionContext) -> list[Finding]:
        try:
            return await agent.run(ctx)
        except _SafetySuppressed:
            return [
                Finding(
                    agent=agent.name,
                    category="filter-suppressed",
                    severity="medium",
                    summary=(
                        f"{agent.name} response was suppressed by Gemini safety "
                        "filters even after compliance-context retry."
                    ),
                )
            ]
        except Exception as exc:  # noqa: BLE001
            logger.exception("Specialist %s failed", agent.name)
            return [
                Finding(
                    agent=agent.name,
                    category="agent-error",
                    severity="critical",
                    summary=f"{type(exc).__name__}: {exc}",
                    raw={"exception_type": type(exc).__name__},
                )
            ]

    _runner.__name__ = f"safe_{agent.name}"
    return _runner
