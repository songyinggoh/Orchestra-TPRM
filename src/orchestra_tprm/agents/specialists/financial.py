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
from orchestra_tprm.schemas import Citation, Finding

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

        return all_findings
