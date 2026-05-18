"""RemediationAgent — mode-aware action plan generator.

Position: after policy (and after pmi_planner in M&A mode).

Skipped when verdict is approve/proceed and there are no findings of
severity >= medium. When skipped, emits an empty RemediationPlan so the
downstream rendering pipeline always has something to consume.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from orchestra.core.context import ExecutionContext
from orchestra.core.types import Message, MessageRole

from orchestra_tprm.agents.base import strip_json_fences
from orchestra_tprm.schemas import Finding, RemediationItem, RemediationPlan

logger = logging.getLogger(__name__)


def should_run_remediation(state: dict[str, Any]) -> bool:
    """True when remediation is worth generating; False to skip."""
    verdict = state.get("policy_verdict") or ""
    ic_memo = state.get("ic_memo") or {}
    ic_rec = ic_memo.get("recommendation") if isinstance(ic_memo, dict) else None

    findings_raw = state.get("findings", [])
    has_medium_plus = False
    for f in findings_raw:
        sev = f.severity if isinstance(f, Finding) else f.get("severity", "")
        if sev in ("medium", "high", "critical"):
            has_medium_plus = True
            break

    approve_set = {"approve", "proceed"}
    is_approve = verdict in approve_set or ic_rec in approve_set
    return not (is_approve and not has_medium_plus)


_VENDOR_SYSTEM = """You are a vendor-onboarding remediation analyst.
For each finding of severity >= medium, write the action the VENDOR must take
before contract signing. Owner is usually "vendor". Leverage refers to a
specific contract clause, certification, or evidence we can demand.

Output a single JSON object:
{
  "items": [
    {
      "finding_id": "<copy from input>",
      "action": "<imperative, specific>",
      "owner": "vendor" | "buyer" | "both",
      "priority": "P0" | "P1" | "P2",
      "leverage": "<contract clause / cert / evidence>",
      "est_effort_days": <int or null>
    }
  ],
  "horizon_days": <int — max est_effort_days across items>,
  "summary": "<1 sentence>"
}
No prose, no Markdown.
"""

_MA_SYSTEM = """You are an M&A deal-structuring analyst.
For each finding of severity >= medium, write the action the BUYER can take to
mitigate it via deal terms: price reduction, indemnity, escrow, rep-and-warranty
insurance, or post-close monitoring. Owner is usually "buyer". Leverage refers
to the specific SPA clause, escrow term, or RWI policy.

Output a single JSON object with the same shape as the vendor mode (items[],
horizon_days, summary). No prose, no Markdown.
"""


class RemediationAgent:
    """Generates a prioritized RemediationPlan from findings, mode-aware."""

    name = "RemediationAgent"

    def __init__(self, *, mode: str, model: str = "gemini-2.5-flash") -> None:
        if mode not in ("vendor", "ma"):
            raise ValueError(f"Unknown mode: {mode}")
        self._mode = mode
        self.model = model

    async def run(self, ctx: ExecutionContext) -> dict[str, Any]:
        return await self.__call__(ctx.state, ctx=ctx)

    async def __call__(
        self, state: dict[str, Any], *, ctx: ExecutionContext | None = None
    ) -> dict[str, Any]:
        if not should_run_remediation(state):
            return {
                "remediation_plan": RemediationPlan(
                    items=[],
                    horizon_days=0,
                    summary="No remediation required — clean approval.",
                )
            }

        findings = self._coerce_findings(state.get("findings", []))
        actionable = [f for f in findings if f.severity in ("medium", "high", "critical")]

        if not actionable or ctx is None:
            return {
                "remediation_plan": RemediationPlan(
                    items=[], horizon_days=0,
                    summary="No actionable findings.",
                )
            }

        system_prompt = _VENDOR_SYSTEM if self._mode == "vendor" else _MA_SYSTEM
        payload = [
            {
                "finding_id": f.id,
                "agent": f.agent,
                "category": f.category,
                "severity": f.severity,
                "summary": f.summary,
            }
            for f in actionable
        ]
        prompt = f"Findings to remediate:\n{json.dumps(payload, indent=2)}\nReturn the JSON object."

        try:
            messages = [
                Message(role=MessageRole.SYSTEM, content=system_prompt),
                Message(role=MessageRole.USER, content=prompt),
            ]
            resp = await ctx.provider.complete(messages=messages, model=self.model)
            text = strip_json_fences(resp.content if hasattr(resp, "content") else str(resp))
            obj = json.loads(text)
        except (json.JSONDecodeError, Exception) as exc:  # noqa: BLE001
            logger.warning("RemediationAgent LLM/parse failed (%s)", exc)
            return {
                "remediation_plan": RemediationPlan(
                    items=[], horizon_days=0,
                    summary="Remediation plan unavailable — parse error or LLM timeout.",
                )
            }

        # LLM may return a bare list instead of the spec'd object — coerce
        # to empty plan rather than crash. (Fail-soft, same as RiskScoreAgent.)
        if not isinstance(obj, dict):
            logger.warning(
                "RemediationAgent: LLM returned non-object JSON (%s); emitting empty plan",
                type(obj).__name__,
            )
            return {
                "remediation_plan": RemediationPlan(
                    items=[], horizon_days=0,
                    summary="Remediation plan unavailable — LLM returned unexpected shape.",
                )
            }

        items_raw = obj.get("items", [])
        items: list[RemediationItem] = []
        for raw in items_raw:
            try:
                items.append(RemediationItem(**raw))
            except Exception:  # noqa: BLE001
                continue

        horizon = int(obj.get("horizon_days", 0))
        if items and horizon == 0:
            horizon = max((i.est_effort_days or 0) for i in items)

        return {
            "remediation_plan": RemediationPlan(
                items=items,
                horizon_days=horizon,
                summary=str(obj.get("summary", "")),
            )
        }

    @staticmethod
    def _coerce_findings(raw: list[Any]) -> list[Finding]:
        return [f if isinstance(f, Finding) else Finding(**f) for f in raw]
