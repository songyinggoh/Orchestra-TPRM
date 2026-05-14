"""ExternalAgent — sanctions exposure and adverse media screening.

Checks the subject name (and any supplementary documents) against sanctions
lists and adverse media signals. Returns one Finding per identified exposure.
"""
from __future__ import annotations

import json

from orchestra.core.context import ExecutionContext

from orchestra_tprm.agents._uri import read_uri
from orchestra_tprm.agents.base import BaseTPRMAgent
from orchestra_tprm.schemas import Citation, Finding

_SYSTEM = """You are a sanctions and adverse-media compliance officer.
Given the subject name and any supporting documents, assess:
  - Sanctions exposure (OFAC SDN, EU, UN lists)
  - PEP (politically exposed person) status
  - Adverse media (fraud, bribery, regulatory action)
For each identified risk, output ONE JSON object in an array:
  - category: short slug e.g. "sanctions", "pep", "adverse-media", "regulatory"
  - severity: "low" | "medium" | "high" | "critical"
  - summary: one sentence describing the exposure
  - source_url: URL of the source if known, or null
Output a JSON ARRAY. No prose, no Markdown fences.
If no risks are found, return [].
"""


class ExternalAgent(BaseTPRMAgent):
    """Vendor and M&A specialist: screens for sanctions, PEP status, and
    adverse media using the subject name from workflow state.

    Document URIs are read from ``ctx.state["routing"]["ExternalAgent"]``
    resolved via ``ctx.state["file_uris"]``. The subject name always appears
    in the prompt regardless of whether documents are attached.
    """

    name = "ExternalAgent"

    def __init__(self, model: str = "gemini-2.5-flash") -> None:
        self.model = model

    async def _emit_findings(self, ctx: ExecutionContext) -> list[Finding]:
        routing: dict = ctx.state.get("routing", {})
        file_uris: dict = ctx.state.get("file_uris", {})
        subject_name: str = ctx.state.get("subject_name", "unknown")
        my_docs: list[str] = routing.get(self.name, [])

        text_chunks: list[str] = []
        attachments: list[dict] = []
        resolved_docs: list[str] = []

        for doc_id in my_docs:
            uri = file_uris.get(doc_id)
            if not uri:
                continue
            resolved_docs.append(doc_id)
            if uri.startswith("https://"):
                attachments.append({"file_uri": uri, "mime_type": "application/pdf"})
            else:
                content = read_uri(uri)
                if content:
                    text_chunks.append(f"=== {doc_id} ===\n{content}")

        # ExternalAgent always runs even with no documents (subject name alone
        # is enough to perform a basic sanctions/PEP screen).
        body = "\n\n".join(text_chunks) if text_chunks else "(no supplementary documents)"
        prompt = (
            f"Subject: {subject_name}\n"
            f"Supporting documents:\n{body}\n"
            "Screen for sanctions, PEP status, and adverse media. "
            "Emit the JSON array as instructed."
        )

        text = await self._call_llm(
            ctx,
            prompt=prompt,
            system=_SYSTEM,
            attachments=attachments or None,
        )

        if not text.strip():
            return []

        try:
            items = json.loads(text)
        except json.JSONDecodeError:
            return [
                Finding(
                    agent=self.name,
                    category="parse-error",
                    severity="critical",
                    summary=f"ExternalAgent: LLM returned non-JSON response: {text[:120]}",
                )
            ]

        if not isinstance(items, list):
            return [
                Finding(
                    agent=self.name,
                    category="parse-error",
                    severity="critical",
                    summary=f"ExternalAgent: expected JSON array, got {type(items).__name__}",
                )
            ]

        primary_doc = resolved_docs[0] if resolved_docs else subject_name
        all_findings: list[Finding] = []
        for item in items:
            all_findings.append(
                Finding(
                    agent=self.name,
                    category=item.get("category", "unknown"),
                    severity=item.get("severity", "low"),
                    summary=item.get("summary", ""),
                    evidence=[
                        Citation(
                            file_id=primary_doc,
                            page=None,
                        )
                    ],
                    raw={k: v for k, v in item.items()
                         if k not in {"category", "severity", "summary"}},
                )
            )
        return all_findings
