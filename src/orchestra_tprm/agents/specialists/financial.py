"""FinancialAgent — M&A financial due-diligence specialist.

Analyses financial statements and regulatory filings for M&A diligence risks.
This agent is null-modelled (model=None) in vendor mode; the graph wiring
layer checks ModeConfig.specialists.financial before including it in the fan-out.
"""
from __future__ import annotations

import json

from orchestra.core.context import ExecutionContext

from orchestra_tprm.agents._uri import read_uri
from orchestra_tprm.agents.base import BaseTPRMAgent, strip_json_fences
from orchestra_tprm.schemas import Citation, Finding, MAScope

_SYSTEM = """You are a senior M&A due-diligence analyst.
Analyse the financial statements / SEC filings provided and identify material
risks relevant to an acquisition decision.
For each metric or risk area, output ONE JSON object in an array:
  - metric: short label e.g. "revenue-growth", "debt-to-equity", "going-concern"
  - value: the specific figure or observation as a string
  - severity: "low" | "medium" | "high" | "critical"
  - summary: one sentence explaining the risk or significance
  - citation_page: integer page in the source document, or null
Output a JSON ARRAY. No prose, no Markdown fences.
If no material risks are found, return [].
"""

_QOE_SYSTEM = """You are a senior M&A quality-of-earnings analyst.
Given the financial findings already extracted and the raw filings, perform an EBITDA normalization pass.
Identify and quantify each adjustment in this list:
  - owner_comp_excess: above-market owner / founder compensation to add back
  - related_party_txns: non-arms-length transactions to reverse
  - non_recurring_revenue: one-time revenue items to strip (litigation settlements, asset sales)
  - one_time_costs: one-time costs to add back (restructuring, legal settlements, deal costs)
  - capitalized_rd_adjustment: capitalized R&D that should be expensed (or vice versa)
  - saas_deferred_revenue_haircut: ASC 805 cost-to-fulfill fair-value haircut to deferred revenue
  - working_capital_peg: 12-month average current assets minus current liabilities, excluding cash, debt, and deal accruals

For EACH non-zero adjustment, output ONE JSON object in an array:
  - adjustment: one of the categories above
  - reported_value_usd: integer or null
  - adjusted_value_usd: integer or null
  - delta_usd: integer (adjusted minus reported; negative means EBITDA shrinks)
  - rationale: one sentence explaining the adjustment
  - citation_page: integer page in source, or null

Also output ONE summary object at the end:
  - adjustment: "qoe_summary"
  - reported_ebitda_usd: integer or null
  - qoe_adjusted_ebitda_usd: integer or null
  - delta_usd: integer (reported - adjusted)

Output a JSON ARRAY. No prose, no Markdown fences. If no adjustments are warranted, return [].
"""


class FinancialAgent(BaseTPRMAgent):
    """M&A-mode specialist: extracts financial risk metrics from filings.

    Document URIs are read from ``ctx.state["routing"]["FinancialAgent"]``
    resolved via ``ctx.state["file_uris"]``. Each document is sent to the LLM
    individually; findings are accumulated across all documents.

    In vendor mode this agent is excluded from the graph (its model is null in
    ModeConfig); the guard below returns [] if called with no docs.
    """

    name = "FinancialAgent"

    def __init__(self, model: str = "gemini-2.5-pro") -> None:
        self.model = model

    async def _emit_findings(self, ctx: ExecutionContext) -> list[Finding]:
        routing: dict = ctx.state.get("routing", {})
        file_uris: dict = ctx.state.get("file_uris", {})
        my_docs: list[str] = routing.get(self.name, [])
        all_findings: list[Finding] = []

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
                "Perform M&A financial due-diligence. Emit the JSON array as instructed."
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
                            f"FinancialAgent: LLM returned non-JSON response "
                            f"for {doc_id}: {text[:120]}"
                        ),
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
                            f"FinancialAgent: expected JSON array for {doc_id}, "
                            f"got {type(items).__name__}"
                        ),
                    )
                )
                continue

            for item in items:
                all_findings.append(
                    Finding(
                        agent=self.name,
                        category=item.get("metric", "financial-risk"),
                        severity=item.get("severity", "low"),
                        summary=item.get("summary", ""),
                        evidence=[
                            Citation(
                                file_id=doc_id,
                                page=item.get("citation_page"),
                            )
                        ],
                        raw={k: v for k, v in item.items()
                             if k not in {"severity", "summary", "citation_page"}},
                    )
                )

        # ---- M&A-mode QoE normalization pass (REQ-06) ----
        if ctx.state.get("mode") == "ma" and all_findings:
            # Resolve MAScope (may be dict from RunRequest or already a model)
            ma_scope_raw = ctx.state.get("ma_scope")
            if isinstance(ma_scope_raw, dict):
                ma_scope: MAScope | None = MAScope(**ma_scope_raw)
            elif isinstance(ma_scope_raw, MAScope):
                ma_scope = ma_scope_raw
            else:
                ma_scope = None

            findings_json = json.dumps(
                [f.model_dump() for f in all_findings], indent=2, default=str
            )
            qoe_prompt = (
                f"Subject: {ctx.state.get('subject_name', 'unknown')}\n"
                f"Existing financial findings:\n{findings_json}\n"
                "Perform the QoE EBITDA normalization pass as instructed."
            )
            qoe_text = await self._call_llm(
                ctx,
                prompt=qoe_prompt,
                system=_QOE_SYSTEM,
                attachments=None,
            )
            if qoe_text.strip():
                try:
                    qoe_items = json.loads(strip_json_fences(qoe_text))
                except json.JSONDecodeError:
                    qoe_items = []

                # Extract summary if present
                reported_ebitda = 0
                qoe_adjusted_ebitda = 0
                ebitda_delta = 0
                for item in qoe_items if isinstance(qoe_items, list) else []:
                    if item.get("adjustment") == "qoe_summary":
                        reported_ebitda = int(item.get("reported_ebitda_usd") or 0)
                        qoe_adjusted_ebitda = int(item.get("qoe_adjusted_ebitda_usd") or 0)
                        ebitda_delta = int(item.get("delta_usd") or 0)

                # Compute implied multiple (cap at 20x, default 8x)
                ev = ma_scope.enterprise_value_usd if ma_scope else None
                if ev and qoe_adjusted_ebitda > 0:
                    implied_multiple = min(20.0, ev / qoe_adjusted_ebitda)
                else:
                    implied_multiple = 8.0
                ebitda_chip_usd = int(abs(ebitda_delta) * implied_multiple)

                # Emit one Finding per non-zero adjustment + a summary Finding
                for item in qoe_items if isinstance(qoe_items, list) else []:
                    adjustment = item.get("adjustment", "qoe-adjustment")
                    if adjustment == "qoe_summary":
                        all_findings.append(
                            Finding(
                                agent=self.name,
                                category="qoe-ebitda-normalization",
                                severity="high" if ebitda_chip_usd > 0 else "low",
                                summary=(
                                    f"QoE normalization: reported EBITDA ${reported_ebitda:,} → "
                                    f"adjusted ${qoe_adjusted_ebitda:,} (delta ${ebitda_delta:,}); "
                                    f"price chip @ {implied_multiple:.1f}x = ${ebitda_chip_usd:,}"
                                ),
                                workstream="financial",
                                ic_decision="price-adjustment" if ebitda_chip_usd > 0 else "post-close-monitoring",
                                exposure_usd_range=(0, ebitda_chip_usd) if ebitda_chip_usd > 0 else None,
                                raw=item,
                            )
                        )
                    else:
                        delta = int(item.get("delta_usd") or 0)
                        all_findings.append(
                            Finding(
                                agent=self.name,
                                category=f"qoe-{adjustment}".replace("_", "-"),
                                severity="medium" if abs(delta) > 0 else "low",
                                summary=item.get("rationale", f"QoE adjustment: {adjustment}"),
                                workstream="financial",
                                ic_decision="price-adjustment" if abs(delta) > 0 else "post-close-monitoring",
                                exposure_usd_range=(0, int(abs(delta) * implied_multiple)) if delta else None,
                                evidence=[
                                    Citation(
                                        file_id="qoe-pass",
                                        page=item.get("citation_page"),
                                    )
                                ],
                                raw=item,
                            )
                        )

        return all_findings
