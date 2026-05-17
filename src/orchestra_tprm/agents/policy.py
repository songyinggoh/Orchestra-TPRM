"""PolicyAgent — diffs findings against the mode's policy pack, computes
a weighted risk score, and writes every finding to BigQuery.

Data-driven invariant: all policy parameters are loaded from the YAML file
referenced by ``ModeConfig.policy_pack`` at construction time. Mode selection
is expressed entirely through configuration — no branching on mode name.

M&A mode: when ``state["ma_scope"]`` is present the agent produces a full
``ICMemo`` (recommendation ∈ {proceed, reprice, walk}) using the 3-tier IC
decision priority order defined in CONTEXT.md.  ``policy_verdict`` mirrors
``ic_memo.recommendation`` for backward compatibility.

Vendor mode: when ``ma_scope`` is absent the legacy YAML-driven verdict rules
(approve / conditional-approve / reject) are preserved unchanged.  An empty
placeholder ``ICMemo`` is still emitted so callers can always access
``state["ic_memo"]`` without a None-check.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from orchestra.core.context import ExecutionContext
from orchestra_tprm.adapters.protocols import BigQueryAdapterP
from orchestra_tprm.modes.config import ModeConfig
from orchestra_tprm.schemas import Finding, ICMemo, ICRiskItem, MAScope


# ---------------------------------------------------------------------------
# Module-level helper mappings
# ---------------------------------------------------------------------------

_IC_TO_MITIGATION: dict[str, str] = {
    "deal-stopper": "CP",                   # condition precedent (must clear before close)
    "price-adjustment": "price-chip",        # reduce purchase price
    "SPA-protection": "indemnity",           # ring-fenced indemnity / warranty
    "post-close-monitoring": "post-close",   # monitor after close
}


def _ic_to_mitigation(ic_decision: str | None) -> str:
    """Map a Finding.ic_decision label to a mitigation type for the risk register.

    Falls back to ``post-close`` when no IC classification is present (e.g. legacy
    findings or filter-suppressed agent errors).
    """
    if ic_decision is None:
        return "post-close"
    return _IC_TO_MITIGATION.get(ic_decision, "post-close")


_SEVERITY_TO_PROBABILITY: dict[str, str] = {
    "critical": "high",
    "high": "high",
    "medium": "medium",
    "low": "low",
}


def _severity_to_probability(severity: str) -> str:
    """Map a Finding.severity to ICRiskItem.probability bucket."""
    return _SEVERITY_TO_PROBABILITY.get(severity, "low")


# ---------------------------------------------------------------------------
# PolicyAgent
# ---------------------------------------------------------------------------


class PolicyAgent:
    """Pure rule-based policy evaluator.

    Reads the policy pack YAML from ``mode_config.policy_pack``, applies
    severity weights to the incoming findings, derives a verdict, and
    appends the findings to BigQuery for audit.

    No LLM call is performed — the agent is deterministic and fast.
    """

    name = "PolicyAgent"

    def __init__(
        self,
        *,
        mode_config: ModeConfig,
        bq: BigQueryAdapterP,
        dataset: str,
        table: str,
    ) -> None:
        self._cfg = mode_config
        self._bq = bq
        self._dataset = dataset
        self._table = table
        self._policy: dict[str, Any] = yaml.safe_load(
            Path(mode_config.policy_pack).read_text(encoding="utf-8")
        )

    async def __call__(
        self,
        state: dict[str, Any],
        *,
        ctx: ExecutionContext | None = None,
    ) -> dict[str, Any]:
        """Evaluate findings and return state patch with risk_score + policy_verdict + ic_memo."""
        raw_findings: list[Any] = state.get("findings", [])

        # Coerce dicts back to Finding objects (graph state may deserialise as dicts)
        coerced: list[Finding] = [
            f if isinstance(f, Finding) else Finding(**f) for f in raw_findings
        ]

        weights: dict[str, int] = self._policy.get("weights", {})
        score: int = sum(weights.get(f.severity, 0) for f in coerced)

        # Resolve optional MAScope (may be dict from RunRequest or a model)
        ma_scope_raw = state.get("ma_scope")
        if isinstance(ma_scope_raw, dict):
            ma_scope: MAScope | None = MAScope(**ma_scope_raw)
        elif isinstance(ma_scope_raw, MAScope):
            ma_scope = ma_scope_raw
        else:
            ma_scope = None

        # IC memo replaces the legacy YAML verdict when ma_scope is present;
        # otherwise vendor mode keeps the legacy reject / conditional / approve string.
        if ma_scope is not None:
            ic_memo = self._build_ic_memo(coerced, ma_scope)
            verdict: str = ic_memo.recommendation
        else:
            ic_memo = ICMemo(
                executive_summary="",
                headline_terms="",
                recommendation="proceed",  # neutral placeholder for vendor mode
                risk_register=[],
            )
            verdict = self._verdict(coerced, score)

        # Audit: append all findings to BigQuery (or fake adapter in tests) — unchanged
        run_id: str = (
            getattr(ctx, "run_id", "unknown") if ctx is not None else "unknown"
        )
        await self._bq.append_findings(
            self._dataset,
            self._table,
            run_id,
            coerced,
            mode=state.get("mode", ""),
            subject=state.get("subject_name", ""),
        )

        return {
            "risk_score": float(score),
            "policy_verdict": verdict,
            "ic_memo": ic_memo.model_dump(),
        }

    def _verdict(self, findings: list[Finding], score: int) -> str:
        """Apply YAML-driven verdict rules. Order matters: most-severe first."""
        rules: dict[str, Any] = self._policy.get("verdict", {})

        # Rule 1: any critical finding → immediate reject
        if rules.get("reject_if_any_critical") and any(
            f.severity == "critical" for f in findings
        ):
            return "reject"

        # Rule 2: score exceeds hard ceiling → reject
        if score > rules.get("reject_above", 30):
            return "reject"

        # Rule 3: score exceeds conditional threshold → conditional-approve
        if score > rules.get("conditional_above", 10):
            return "conditional-approve"

        # Default: approve
        return "approve"

    def _build_ic_memo(
        self,
        findings: list[Finding],
        ma_scope: MAScope | None,
    ) -> ICMemo:
        """Build an ICMemo from coerced findings + optional MAScope.

        Priority order (CONTEXT.md):
          1. Any finding with ic_decision='deal-stopper' OR matching a MAScope deal-breaker
             keyword (case-insensitive substring on finding.summary) → recommendation='walk'.
          2. Sum of upper-bound exposures > MAScope.materiality_threshold_usd → 'reprice'.
          3. Otherwise → 'proceed'.
        """
        # Priority 1: deal-stoppers (either tagged or matched against MAScope deal-breakers)
        deal_stoppers = [f for f in findings if f.ic_decision == "deal-stopper"]
        if ma_scope is not None:
            for f in findings:
                for breaker in ma_scope.deal_breakers:
                    if breaker and breaker.lower() in (f.summary or "").lower():
                        if f not in deal_stoppers:
                            deal_stoppers.append(f)
                        break

        recommendation: str
        if deal_stoppers:
            recommendation = "walk"
        else:
            # Priority 2: total upper-bound exposure vs materiality threshold
            total_upper = sum(
                (f.exposure_usd_range[1] if f.exposure_usd_range is not None else 0)
                for f in findings
            )
            threshold = ma_scope.materiality_threshold_usd if ma_scope else None
            if threshold is not None and total_upper > threshold:
                recommendation = "reprice"
            else:
                recommendation = "proceed"

        # Build risk register: one ICRiskItem per finding that has an ic_decision tag
        risk_register: list[ICRiskItem] = []
        for idx, f in enumerate(findings):
            if f.ic_decision is None:
                continue
            finding_id = getattr(f, "id", None) or f"finding-{idx}"
            risk_register.append(
                ICRiskItem(
                    finding_id=str(finding_id),
                    workstream=f.workstream or "unknown",
                    exposure_usd_range=f.exposure_usd_range,
                    mitigation=_ic_to_mitigation(f.ic_decision),  # type: ignore[arg-type]
                    probability=_severity_to_probability(f.severity),  # type: ignore[arg-type]
                )
            )

        # Headline terms (one-line summary of recommendation + top exposure)
        top_exposure = 0
        for f in findings:
            if f.exposure_usd_range is not None:
                top_exposure = max(top_exposure, f.exposure_usd_range[1])
        headline = (
            f"Recommendation: {recommendation.upper()}; "
            f"top single-finding exposure ~${top_exposure:,}"
            if top_exposure
            else f"Recommendation: {recommendation.upper()}"
        )

        return ICMemo(
            executive_summary="",  # left blank; Coordinator (Plan 07) may inject narrative
            headline_terms=headline,
            recommendation=recommendation,  # type: ignore[arg-type]
            risk_register=risk_register,
        )
