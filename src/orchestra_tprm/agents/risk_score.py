"""RiskScoreAgent — deterministic math + LLM rationale + fail-soft fallback.

Position: between specialists-join and policy.

Math is computed in Python; the LLM is used only to produce the explanation
string and the three driver one-liners. If the LLM call fails (quota, safety,
network), the agent falls back to template strings derived from finding
metadata so the demo never crashes.

Writes to state["risk_assessment"] (RiskScore object). The legacy
state["risk_score"] (float, written by PolicyAgent) is left untouched.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from orchestra.core.context import ExecutionContext

from orchestra_tprm.agents.base import strip_json_fences
from orchestra_tprm.schemas import Finding, RiskDriver, RiskScore

logger = logging.getLogger(__name__)

_SYSTEM = """You are a vendor risk analyst. Given a list of risk findings, write:
  - "explanation": a 1-2 sentence summary of the risk profile
  - "driver_one_liners": exactly N short sentences (<= 20 words each), one per driver, in order

Output a single JSON object. No prose, no Markdown.
"""


class RiskScoreAgent:
    """Computes 0-100 risk score + verdict + per-dimension breakdown.

    Public surface:
      __call__(state, *, ctx) -> {"risk_assessment": RiskScore}

    Plain callable (not BaseTPRMAgent) because it does not emit Findings.
    """

    name = "RiskScoreAgent"

    def __init__(self, *, policy: dict[str, Any], model: str = "gemini-2.5-flash") -> None:
        self._weights: dict[str, int] = policy.get("weights", {
            "low": 1, "medium": 3, "high": 7, "critical": 15,
        })
        thresholds = policy.get("risk_score_thresholds", {"green_max": 30, "amber_max": 69})
        self._green_max = int(thresholds["green_max"])
        self._amber_max = int(thresholds["amber_max"])
        self.model = model

    async def run(self, ctx: ExecutionContext) -> dict[str, Any]:
        """Convenience wrapper for direct invocation (mirrors specialist agents)."""
        return await self.__call__(ctx.state, ctx=ctx)

    async def __call__(
        self, state: dict[str, Any], *, ctx: ExecutionContext | None = None
    ) -> dict[str, Any]:
        findings = self._coerce_findings(state.get("findings", []))

        if not findings:
            return {
                "risk_assessment": RiskScore(
                    overall=0,
                    verdict="green",
                    dimensions={},
                    top_risk_drivers=[],
                    explanation="No findings emitted by specialists.",
                )
            }

        overall = self._score(findings)
        verdict = self._verdict(overall)
        dimensions = self._dimensions(findings)
        drivers_findings = self._top_drivers(findings, n=3)

        driver_shells = [
            RiskDriver(
                dimension=f.agent.replace("Agent", "").lower(),
                finding_id=f.id,
                severity=f.severity,
                one_liner="",
            )
            for f in drivers_findings
        ]

        explanation, one_liners = await self._narrate(ctx, drivers_findings, dimensions)

        for i, d in enumerate(driver_shells):
            d.one_liner = (
                one_liners[i] if i < len(one_liners) and one_liners[i]
                else drivers_findings[i].summary[:120]
            )

        return {
            "risk_assessment": RiskScore(
                overall=overall,
                verdict=verdict,
                dimensions=dimensions,
                top_risk_drivers=driver_shells,
                explanation=explanation,
            )
        }

    def _verdict(self, overall: int) -> str:
        if overall <= self._green_max:
            return "green"
        if overall <= self._amber_max:
            return "amber"
        return "red"

    def _score(self, findings: list[Finding]) -> int:
        weighted = sum(self._weights.get(f.severity, 0) for f in findings)
        max_possible = max(len(findings), 1) * self._weights.get("critical", 15)
        overall = round(100 * weighted / max_possible)
        return min(100, max(0, overall))

    def _dimensions(self, findings: list[Finding]) -> dict[str, int]:
        by_agent: dict[str, list[Finding]] = {}
        for f in findings:
            key = f.agent.replace("Agent", "").lower()
            by_agent.setdefault(key, []).append(f)
        return {dim: self._score(items) for dim, items in by_agent.items()}

    def _top_drivers(self, findings: list[Finding], *, n: int) -> list[Finding]:
        return sorted(findings, key=lambda f: -self._weights.get(f.severity, 0))[:n]

    async def _narrate(
        self,
        ctx: ExecutionContext | None,
        drivers: list[Finding],
        dimensions: dict[str, int],
    ) -> tuple[str, list[str]]:
        if ctx is None or not drivers:
            return self._fallback(dimensions, drivers)

        prompt_payload = {
            "drivers": [
                {"dim": f.agent, "severity": f.severity, "summary": f.summary}
                for f in drivers
            ],
            "dimensions": dimensions,
        }
        prompt = f"Findings:\n{json.dumps(prompt_payload, indent=2)}\nReturn the JSON object."

        try:
            from orchestra.core.types import Message, MessageRole
            messages = [
                Message(role=MessageRole.SYSTEM, content=_SYSTEM),
                Message(role=MessageRole.USER, content=prompt),
            ]
            resp = await ctx.provider.complete(messages=messages, model=self.model)
            text = strip_json_fences(resp.content if hasattr(resp, "content") else str(resp))
            obj = json.loads(text)
            explanation = str(obj.get("explanation", "")).strip()
            one_liners = [str(s) for s in obj.get("driver_one_liners", [])]
            if not explanation or not one_liners:
                raise ValueError("LLM response missing required fields")
            return explanation, one_liners
        except Exception as exc:  # noqa: BLE001 — fail-soft is the design
            logger.warning("RiskScoreAgent LLM call failed (%s), using fallback", exc)
            return self._fallback(dimensions, drivers)

    def _fallback(
        self, dimensions: dict[str, int], drivers: list[Finding]
    ) -> tuple[str, list[str]]:
        top_dims = sorted(dimensions.items(), key=lambda kv: -kv[1])[:2]
        if top_dims:
            dims_str = ", ".join(name for name, _ in top_dims)
            explanation = f"Risk concentrated in {dims_str}."
        else:
            explanation = "Risk profile not narratable."
        one_liners = [f.summary[:120] for f in drivers]
        return explanation, one_liners

    @staticmethod
    def _coerce_findings(raw: list[Any]) -> list[Finding]:
        return [f if isinstance(f, Finding) else Finding(**f) for f in raw]
