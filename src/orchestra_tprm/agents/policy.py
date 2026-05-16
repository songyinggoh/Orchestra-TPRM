"""PolicyAgent — diffs findings against the mode's policy pack, computes
a weighted risk score, and writes every finding to BigQuery.

Data-driven invariant: all policy parameters are loaded from the YAML file
referenced by ``ModeConfig.policy_pack`` at construction time. Mode selection
is expressed entirely through configuration — no branching on mode name.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from orchestra.core.context import ExecutionContext
from orchestra_tprm.adapters.protocols import BigQueryAdapterP
from orchestra_tprm.modes.config import ModeConfig
from orchestra_tprm.schemas import Finding


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
        """Evaluate findings and return state patch with risk_score + policy_verdict."""
        raw_findings: list[Any] = state.get("findings", [])

        # Coerce dicts back to Finding objects (graph state may deserialise as dicts)
        coerced: list[Finding] = [
            f if isinstance(f, Finding) else Finding(**f) for f in raw_findings
        ]

        weights: dict[str, int] = self._policy.get("weights", {})
        score: int = sum(weights.get(f.severity, 0) for f in coerced)
        verdict: str = self._verdict(coerced, score)

        # Audit: append all findings to BigQuery (or fake adapter in tests)
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

        return {"risk_score": float(score), "policy_verdict": verdict}

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
