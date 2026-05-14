"""PolicyAgent — evaluates specialist findings against a loaded policy pack.

This is a plain async callable node (not a BaseTPRMAgent subclass) because it
produces risk_score + policy_verdict rather than Findings. Wire into the graph
as a closure with the policy pack path injected at build time::

    graph.add_node("policy", lambda state: policy_node(state, policy_pack_path))

Returns:
    ``{"risk_score": float, "policy_verdict": str}``
"""
from __future__ import annotations

import yaml


_DEFAULT_WEIGHT = 3  # fallback for unknown severity strings


def _get_severity(finding: object) -> str:
    """Return the severity string from a Finding object or a plain dict."""
    if isinstance(finding, dict):
        return str(finding.get("severity", "medium")).lower()
    return str(getattr(finding, "severity", "medium")).lower()


async def policy_node(state: dict, policy_pack_path: str) -> dict:
    """Evaluate findings in *state* against the policy pack at *policy_pack_path*.

    Parameters
    ----------
    state:
        Workflow state dict.  ``state["findings"]`` may contain ``Finding``
        instances or plain ``dict`` objects.
    policy_pack_path:
        Absolute path to a YAML policy file (vendor.yaml or ma.yaml).

    Returns
    -------
    dict
        ``{"risk_score": float, "policy_verdict": str}``
    """
    with open(policy_pack_path, encoding="utf-8") as fh:
        pack = yaml.safe_load(fh)

    weights: dict[str, int] = pack.get("risk_score_weights", {})
    rules: list[dict] = pack.get("verdict_rules", [])

    findings: list = state.get("findings", [])

    # --- Compute risk score ---
    raw_score: float = 0.0
    for finding in findings:
        sev = _get_severity(finding)
        raw_score += weights.get(sev, _DEFAULT_WEIGHT)

    risk_score = min(raw_score, 100.0)

    # --- Apply verdict rules (first match wins) ---
    verdict = "approve"  # safe fallback if no rules defined
    for rule in rules:
        condition: dict = rule.get("condition", {})

        if not condition:
            # Empty dict — default/catch-all rule always matches
            verdict = rule["verdict"]
            break

        req_severity: str = condition.get("severity", "")
        min_count: int = condition.get("min_count", 1)

        if req_severity:
            matching = sum(
                1 for f in findings if _get_severity(f) == req_severity.lower()
            )
            if matching >= min_count:
                verdict = rule["verdict"]
                break

    return {"risk_score": round(risk_score, 1), "policy_verdict": verdict}
