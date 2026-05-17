"""SaaSMetricsAgent — M&A-mode SaaS metrics specialist.

Extracts SaaS-specific metrics (ARR, NRR/NDR, GRR, CAC payback, LTV:CAC,
logo retention, Rule of 40, API concentration) from routed financial /
investor documents. Each metric is checked against locked red-flag
thresholds and assigned an ic_decision tag (deal-stopper / price-adjustment
/ SPA-protection / post-close-monitoring) directly by the LLM, with the
threshold table embedded in the system prompt.

M&A-mode only: enabled when ``ModeConfig.specialists.saas_metrics`` is set
(which is true only in ``ma.yaml``). Vendor mode does not instantiate this
agent.
"""
from __future__ import annotations

import json

from orchestra.core.context import ExecutionContext

from orchestra_tprm.agents._uri import read_uri
from orchestra_tprm.agents.base import BaseTPRMAgent, strip_json_fences
from orchestra_tprm.schemas import Citation, Finding

_SYSTEM = """You are a SaaS M&A due-diligence analyst.
Analyse the financial / investor / metrics documents provided and extract these SaaS metrics:
  - arr_usd: Annual Recurring Revenue (USD, integer)
  - nrr_pct: Net Revenue Retention (%)
  - grr_pct: Gross Revenue Retention (%)
  - logo_retention_pct: Logo retention (%)
  - cac_payback_months: CAC payback period (months)
  - ltv_cac_ratio: LTV to CAC ratio
  - rule_of_40: Growth rate + EBITDA margin (sum)
  - api_concentration_pct: Largest single API/customer contract as % of ARR
  - seat_vs_usage_mix: revenue mix between seat-based and usage-based pricing

Apply these RED-FLAG THRESHOLDS to assign ic_decision per metric:
  - NRR < 100% → ic_decision: "price-adjustment"
  - NRR < 90% → ic_decision: "deal-stopper"
  - Logo retention < 85% → ic_decision: "deal-stopper"
  - GRR < 80% (SMB context) → ic_decision: "price-adjustment"
  - CAC payback > 24 months → ic_decision: "price-adjustment"
  - Rule of 40 < 20 → ic_decision: "price-adjustment"
  - API contract concentration > 40% ARR → ic_decision: "SPA-protection"
  - Otherwise → ic_decision: "post-close-monitoring"

For each metric you find, output ONE JSON object in an array:
  - metric: short label (e.g. "nrr", "logo-retention", "rule-of-40")
  - value_pct: numeric value as a string (e.g. "92", "$45M ARR", "26 months")
  - threshold_breached: true | false
  - severity: "low" | "medium" | "high" | "critical"
  - ic_decision: one of "deal-stopper" | "price-adjustment" | "SPA-protection" | "post-close-monitoring"
  - exposure_usd_low: integer (estimated exposure floor in USD), or null
  - exposure_usd_high: integer (estimated exposure ceiling in USD), or null
  - summary: one sentence explaining the metric and its risk implication
  - citation_page: integer page in the source document, or null

Output a JSON ARRAY. No prose, no Markdown fences.
If no SaaS metrics can be extracted, return [].
"""


class SaaSMetricsAgent(BaseTPRMAgent):
    """M&A-mode SaaS metrics specialist.

    Document URIs are read from ``ctx.state["routing"]["SaaSMetricsAgent"]``
    resolved via ``ctx.state["file_uris"]``. Each document is sent to the LLM
    individually; findings are accumulated across all documents. If no
    documents are routed to this agent, a single informational Finding is
    emitted so the run produces a paper trail of the "no SaaS docs"
    condition rather than silently returning [].
    """

    name = "SaaSMetricsAgent"

    def __init__(self, model: str = "gemini-2.5-pro") -> None:
        self.model = model

    async def _emit_findings(self, ctx: ExecutionContext) -> list[Finding]:
        routing: dict = ctx.state.get("routing", {})
        file_uris: dict = ctx.state.get("file_uris", {})
        my_docs: list[str] = routing.get(self.name, [])
        all_findings: list[Finding] = []

        # Fallback: no docs routed → emit one informational Finding
        if not my_docs:
            return [
                Finding(
                    agent=self.name,
                    category="saas-metrics-no-docs",
                    severity="low",
                    summary=(
                        "No financial / investor documents were routed to "
                        "SaaSMetricsAgent — SaaS metrics could not be assessed."
                    ),
                    workstream="financial",
                    ic_decision="post-close-monitoring",
                )
            ]

        for doc_id in my_docs:
            uri = file_uris.get(doc_id)
            if not uri:
                continue

            if uri.startswith("https://"):
                attachments: list[dict] | None = [
                    {"file_uri": uri, "mime_type": "application/pdf"}
                ]
                body = ""
            else:
                try:
                    content = read_uri(uri)
                except (FileNotFoundError, OSError, UnicodeDecodeError):
                    content = ""
                attachments = None
                if not content:
                    continue
                body = content

            prompt = (
                f"Subject: {ctx.state.get('subject_name', 'unknown')}\n"
                f"Document: {doc_id}\n"
                f"{body}\n"
                "Extract SaaS metrics and apply the red-flag thresholds. "
                "Emit the JSON array as instructed."
            )

            text = await self._call_llm(
                ctx,
                prompt=prompt,
                system=_SYSTEM,
                attachments=attachments,
            )

            if not text.strip():
                continue

            try:
                items = json.loads(strip_json_fences(text))
            except json.JSONDecodeError:
                all_findings.append(
                    Finding(
                        agent=self.name,
                        category="parse-error",
                        severity="critical",
                        summary=(
                            f"SaaSMetricsAgent: LLM returned non-JSON response "
                            f"for {doc_id}: {text[:120]}"
                        ),
                        workstream="financial",
                    )
                )
                continue

            if not isinstance(items, list):
                all_findings.append(
                    Finding(
                        agent=self.name,
                        category="parse-error",
                        severity="critical",
                        summary=(
                            f"SaaSMetricsAgent: expected JSON array for {doc_id}, "
                            f"got {type(items).__name__}"
                        ),
                        workstream="financial",
                    )
                )
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue
                metric = item.get("metric", "saas-metric")
                ic_raw = item.get("ic_decision")
                if ic_raw not in {
                    "deal-stopper",
                    "price-adjustment",
                    "SPA-protection",
                    "post-close-monitoring",
                }:
                    ic_raw = "post-close-monitoring"

                lo = item.get("exposure_usd_low")
                hi = item.get("exposure_usd_high")
                exposure_range: tuple[int, int] | None
                if lo is not None and hi is not None:
                    try:
                        exposure_range = (int(lo), int(hi))
                    except (TypeError, ValueError):
                        exposure_range = None
                else:
                    exposure_range = None

                all_findings.append(
                    Finding(
                        agent=self.name,
                        category=f"saas-{metric}".replace("_", "-"),
                        severity=item.get("severity", "low"),
                        summary=item.get("summary", ""),
                        evidence=[
                            Citation(
                                file_id=doc_id,
                                page=item.get("citation_page"),
                            )
                        ],
                        workstream="financial",
                        ic_decision=ic_raw,
                        exposure_usd_range=exposure_range,
                        raw={
                            k: v
                            for k, v in item.items()
                            if k
                            not in {
                                "severity",
                                "summary",
                                "citation_page",
                                "ic_decision",
                                "exposure_usd_low",
                                "exposure_usd_high",
                            }
                        },
                    )
                )

        return all_findings
