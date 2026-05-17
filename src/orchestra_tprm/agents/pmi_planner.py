"""PMIPlannerAgent — Phase 4 output for M&A mode.

Consumes the accumulated findings (after PolicyAgent has tagged them with
ic_decision and the Coordinator has written the deal memo) and produces a
100-day Post-Merger Integration plan mapped to integration workstreams
with deadline tier assignments (day-30, day-60, day-100, day-180).

Follows the same callable-agent pattern as PolicyAgent / Coordinator (NOT
a specialist subclass): instantiated once at graph build time and
invoked with ``state, *, ctx`` returning a state patch dict.
"""
from __future__ import annotations

import json
from typing import Any

from orchestra.core.context import ExecutionContext
from orchestra.core.types import Message, MessageRole

from orchestra_tprm.agents.base import strip_json_fences
from orchestra_tprm.schemas import Finding, PMIItem, PMIPlan

_SYSTEM = """You are a senior post-merger integration (PMI) planner.
Given a list of M&A due-diligence findings (each with workstream + ic_decision +
optional exposure_usd_range), produce a 100-day PMI plan mapping each material
finding to an integration action with a deadline tier.

Deadline tier assignment rules:
  - day-30:  deal-stopper findings that were overridden; security/tech critical findings;
             Day-1 legal entity actions (corporate filings, signatory authority)
  - day-60:  IT integration (identity / SSO / directory consolidation, application landscape);
             HR retention package rollouts; commercial customer notification waves
  - day-100: Process / operational alignment (finance close cadence, procurement
             consolidation, vendor rationalisation); ESG policy alignment
  - day-180: Strategic optimisation; long-tail data migration; brand consolidation

Each PMI action MUST cite which workstream it belongs to (legal, financial, tech,
commercial, hr, esg, regulatory) and assign a clear owner role (e.g. "GC", "CIO",
"CHRO", "Integration PMO", "CFO").

Output a single JSON object with this shape (no prose, no Markdown fences):
  {
    "summary": "<one-paragraph 100-day plan overview>",
    "items": [
      {
        "workstream": "<one of: legal, financial, tech, commercial, hr, esg, regulatory>",
        "action": "<imperative-mood action sentence>",
        "deadline_tier": "<one of: day-30, day-60, day-100, day-180>",
        "owner": "<role label>",
        "dependency": "<id or null>"
      }
    ]
  }

If no findings warrant a PMI action, output:
  {"summary": "No PMI actions warranted — clean diligence with no material risks.", "items": []}
"""


_VALID_TIERS = {"day-30", "day-60", "day-100", "day-180"}
_VALID_WORKSTREAMS = {
    "legal",
    "financial",
    "tech",
    "commercial",
    "hr",
    "esg",
    "regulatory",
}


class PMIPlannerAgent:
    """Callable agent that produces a PMIPlan from accumulated findings.

    Mirrors the PolicyAgent / Coordinator shape: constructed once with a model
    name, invoked with ``state, *, ctx``. The graph (Plan 06) wires this agent
    after the Coordinator in M&A mode only, via a ``_SpecShim``-style wrapper.
    """

    name = "PMIPlannerAgent"

    def __init__(self, model: str = "gemini-2.5-pro") -> None:
        self.model = model

    async def __call__(
        self,
        state: dict[str, Any],
        *,
        ctx: ExecutionContext | None = None,
    ) -> dict[str, Any]:
        """Build a PMIPlan from state['findings'] and return a state patch dict."""
        raw_findings: list[Any] = state.get("findings", [])
        coerced: list[Finding] = [
            f if isinstance(f, Finding) else Finding(**f) for f in raw_findings
        ]

        # Only consider findings that have an ic_decision tag — vendor-mode
        # findings without an ic_decision are not PMI-relevant.
        ic_findings = [f for f in coerced if f.ic_decision is not None]

        if not ic_findings:
            empty_plan = PMIPlan(
                summary=(
                    "No PMI actions warranted — no IC-classified findings "
                    "produced by the diligence run."
                ),
                items=[],
            )
            return {"pmi_plan": empty_plan.model_dump()}

        # No provider available (test / local run with no LLM) → deterministic
        # fallback that synthesises a PMI plan from the ic_decision + workstream
        # tags using the locked tier-assignment rules.
        if ctx is None or getattr(ctx, "provider", None) is None:
            plan = self._fallback_plan(ic_findings)
            return {"pmi_plan": plan.model_dump()}

        findings_json = json.dumps(
            [f.model_dump() for f in ic_findings], indent=2, default=str
        )
        subject = state.get("subject_name", "unknown")
        user_prompt = (
            f"Subject: {subject}\n"
            f"Findings (each with workstream + ic_decision):\n{findings_json}\n"
            "Produce the PMI 100-day plan JSON object as instructed."
        )

        msgs = [
            Message(role=MessageRole.SYSTEM, content=_SYSTEM),
            Message(role=MessageRole.USER, content=user_prompt),
        ]
        resp = await ctx.provider.complete(msgs, model=self.model)
        text = (resp.content or "").strip()

        if not text:
            plan = self._fallback_plan(ic_findings)
            return {"pmi_plan": plan.model_dump()}

        try:
            payload = json.loads(strip_json_fences(text))
        except json.JSONDecodeError:
            plan = self._fallback_plan(ic_findings)
            plan.summary = (
                f"PMI plan generated by deterministic fallback — LLM "
                f"returned non-JSON: {text[:120]}"
            )
            return {"pmi_plan": plan.model_dump()}

        if not isinstance(payload, dict):
            plan = self._fallback_plan(ic_findings)
            return {"pmi_plan": plan.model_dump()}

        # Build PMIItem list, validating each item defensively.
        raw_items = payload.get("items") or []
        items: list[PMIItem] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            workstream = str(raw.get("workstream", "")).lower()
            if workstream not in _VALID_WORKSTREAMS:
                continue
            tier = str(raw.get("deadline_tier", ""))
            if tier not in _VALID_TIERS:
                tier = "day-100"
            action = str(raw.get("action", "")).strip()
            if not action:
                continue
            owner = str(raw.get("owner", "Integration PMO")).strip() or "Integration PMO"
            dependency = raw.get("dependency")
            if dependency is not None and not isinstance(dependency, str):
                dependency = str(dependency)
            items.append(
                PMIItem(
                    workstream=workstream,
                    action=action,
                    deadline_tier=tier,  # type: ignore[arg-type]
                    owner=owner,
                    dependency=dependency,
                )
            )

        plan = PMIPlan(
            summary=str(payload.get("summary", "")).strip()
            or f"PMI 100-day plan for {subject} ({len(items)} actions).",
            items=items,
        )
        return {"pmi_plan": plan.model_dump()}

    # ------------------------------------------------------------------
    # Deterministic fallback (no LLM available)
    # ------------------------------------------------------------------

    @staticmethod
    def _tier_for_finding(f: Finding) -> str:
        """Apply CONTEXT.md PMI Deadline Tier Assignment Logic."""
        ws = (f.workstream or "").lower()
        ic = f.ic_decision
        sev = f.severity

        # Tier 1: critical security/tech findings + overridden deal-stoppers + day-1 legal
        if sev == "critical" and ws in {"tech", "regulatory"}:
            return "day-30"
        if ic == "deal-stopper":
            return "day-30"
        if ws == "legal" and sev in {"high", "critical"}:
            return "day-30"

        # Tier 2: IT integration + HR retention
        if ws == "tech":
            return "day-60"
        if ws == "hr":
            return "day-60"

        # Tier 3: process / operational
        if ws in {"financial", "commercial"}:
            return "day-100"

        # Tier 4: strategic / long-tail (esg, regulatory non-critical, anything else)
        return "day-180"

    @staticmethod
    def _owner_for_workstream(ws: str) -> str:
        return {
            "legal": "General Counsel",
            "financial": "CFO",
            "tech": "CIO",
            "commercial": "Chief Revenue Officer",
            "hr": "CHRO",
            "esg": "Chief Sustainability Officer",
            "regulatory": "Chief Compliance Officer",
        }.get(ws, "Integration PMO")

    def _fallback_plan(self, findings: list[Finding]) -> PMIPlan:
        items: list[PMIItem] = []
        for f in findings:
            ws = (f.workstream or "").lower()
            if ws not in _VALID_WORKSTREAMS:
                ws = "regulatory"
            tier = self._tier_for_finding(f)
            action = f"Remediate: {f.summary}" if f.summary else f"Address {f.category} finding"
            items.append(
                PMIItem(
                    workstream=ws,  # type: ignore[arg-type]
                    action=action,
                    deadline_tier=tier,  # type: ignore[arg-type]
                    owner=self._owner_for_workstream(ws),
                    dependency=None,
                )
            )
        return PMIPlan(
            summary=(
                f"PMI 100-day plan synthesised from {len(items)} IC-classified "
                "findings using deterministic tier-assignment rules (no LLM available)."
            ),
            items=items,
        )
