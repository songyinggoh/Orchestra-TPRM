"""LegalAgent — extracts risky clauses from MSAs/DPAs/contracts.

Specialist for vendor-mode contract review. Uses gemini-2.5-flash to parse
contract documents and identify clause-level risks across liability,
IP ownership, indemnification, termination, data-protection, and
change-of-control categories.

Each routed document is queried independently; findings from all documents
are aggregated and returned as a flat list[Finding].
"""
from __future__ import annotations

import json

from orchestra.core.context import ExecutionContext

from orchestra_tprm.agents.base import BaseTPRMAgent
from orchestra_tprm.schemas import Citation, Finding

_SYSTEM = """You are a senior commercial-contracts attorney auditing a third-party agreement.
For each risky clause you identify, output one JSON object with these fields:
  - category: short slug (e.g. "liability", "ip-assignment", "indemnity", "termination", "data-protection", "change-of-control")
  - severity: "low" | "medium" | "high" | "critical"
  - summary: one sentence describing the risk
  - citation_page: integer page number from the document
  - clause_id: section identifier as written in the document
Output a JSON ARRAY of these objects. No prose, no Markdown.
If the document is not a contract, return [].
"""


class LegalAgent(BaseTPRMAgent):
    """Reviews contract documents for clause-level risk findings.

    Accepts a list of document IDs via ``ctx.state["routing"]["LegalAgent"]``
    and resolves their URIs from ``ctx.state["file_uris"]``. Each document
    is sent to the LLM individually; findings are accumulated across all
    documents.

    Attachments are only passed when the URI is an ``https://`` Gemini Files
    API URI (multimodal). Local/fake URIs skip attachments and rely on
    the prompt text alone (sufficient for unit tests with ScriptedLLM).
    """

    name = "LegalAgent"

    def __init__(self, model: str = "gemini-2.5-flash") -> None:
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

            # Only attach multimodal file references for real Gemini Files API URIs
            attachments = (
                [{"file_uri": uri, "mime_type": "application/pdf"}]
                if uri.startswith("https://")
                else None
            )

            prompt = (
                f"Subject: {ctx.state.get('subject_name', 'unknown')}\n"
                f"Document: {doc_id}\n"
                "Audit the attached contract. Output the JSON array as instructed."
            )

            text = await self._call_llm(
                ctx, prompt=prompt, system=_SYSTEM, attachments=attachments
            )
            if not text.strip():
                continue

            try:
                items = json.loads(text)
            except json.JSONDecodeError:
                continue

            for item in items:
                all_findings.append(
                    Finding(
                        agent=self.name,
                        category=item.get("category", "unknown"),
                        severity=item.get("severity", "low"),
                        summary=item.get("summary", ""),
                        evidence=[
                            Citation(
                                file_id=doc_id,
                                page=item.get("citation_page"),
                                snippet=item.get("clause_id", ""),
                            )
                        ],
                        raw=item,
                    )
                )

        return all_findings
