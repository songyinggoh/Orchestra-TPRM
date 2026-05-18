"""ESGAgent — 7th specialist for ESG disclosure review.

Reviews vendor's ESG disclosures (sustainability report, governance docs,
diversity report, supplier code of conduct) and emits findings against the
Environmental / Social / Governance checklist defined in the system prompt.

Active in both vendor and M&A modes.
"""
from __future__ import annotations

import json

from orchestra.core.context import ExecutionContext

from orchestra_tprm.agents._uri import read_uri
from orchestra_tprm.agents.base import BaseTPRMAgent, strip_json_fences
from orchestra_tprm.schemas import Citation, Finding

_SYSTEM = """You are an ESG (Environmental, Social, Governance) compliance analyst.
For each gap or risk you identify, output one JSON object with these fields:
  - category: short slug from the controlled vocabulary below
  - severity: "low" | "medium" | "high" | "critical"
  - summary: one sentence describing the gap
  - citation_page: integer page number, or null

Controlled categories:
Environmental:
  - "net-zero-commitment" (critical if no target year disclosed)
  - "scope-emissions-disclosure" (high if Scope 3 missing, medium if Scope 1+2 only)
  - "renewable-energy-mix" (low-medium)
  - "e-waste-policy" (low-medium)
Social:
  - "dei-metrics" (medium-high)
  - "supply-chain-labour-audit" (medium-high)
  - "modern-slavery-statement" (high if missing, critical if non-compliant w/ MSA 2015)
  - "customer-privacy-framework" (medium)
Governance:
  - "board-independence" (medium-high)
  - "audit-committee" (medium)
  - "anti-corruption-policy" (high if missing, critical if known violation)
  - "whistleblower-protection" (medium)
  - "security-audit-cadence" (medium-high)

Output a JSON ARRAY of objects. No prose, no Markdown.
If documents fully disclose against this checklist with no gaps, return [].
"""


class ESGAgent(BaseTPRMAgent):
    """Reviews ESG disclosure documents and emits per-gap findings."""

    name = "ESGAgent"

    def __init__(self, model: str = "gemini-2.5-flash") -> None:
        self.model = model

    async def _emit_findings(self, ctx: ExecutionContext) -> list[Finding]:
        file_uris: dict[str, str] = ctx.state.get("file_uris", {})
        routing: dict[str, list[str]] = ctx.state.get("routing", {})
        my_docs = routing.get(self.name, [])

        if not my_docs:
            return [
                Finding(
                    agent=self.name,
                    category="esg-no-docs",
                    severity="low",
                    summary=(
                        "No ESG disclosure documents were routed to ESGAgent — "
                        "ESG posture could not be assessed."
                    ),
                )
            ]

        all_findings: list[Finding] = []
        for doc_id in my_docs:
            uri = file_uris.get(doc_id)
            if not uri:
                continue
            attachments = None
            try:
                content = read_uri(uri)
            except (FileNotFoundError, OSError, UnicodeDecodeError):
                content = ""
            if not content:
                continue
            body = content

            prompt = (
                f"Subject: {ctx.state.get('subject_name', 'unknown')}\n"
                f"Document: {doc_id}\n"
                f"{body}\n"
                "Review the document above against the ESG checklist. "
                "Output the JSON array as instructed."
            )

            text = await self._call_llm(
                ctx, prompt=prompt, system=_SYSTEM, attachments=attachments
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
                        severity="high",
                        summary=f"ESGAgent: LLM returned non-JSON for {doc_id}: {text[:120]}",
                        evidence=[Citation(file_id=doc_id)],
                    )
                )
                continue

            for item in items:
                page = item.get("citation_page")
                all_findings.append(
                    Finding(
                        agent=self.name,
                        category=item.get("category", "unspecified"),
                        severity=item.get("severity", "medium"),
                        summary=item.get("summary", ""),
                        evidence=[
                            Citation(
                                file_id=doc_id,
                                page=int(page) if page is not None else None,
                            )
                        ],
                    )
                )

        return all_findings
