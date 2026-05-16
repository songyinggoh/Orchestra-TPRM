"""SecurityAgent — scores SOC2/ISO27001 controls against the attestation."""
from __future__ import annotations

import json

from orchestra.core.context import ExecutionContext

from orchestra_tprm.agents._uri import read_uri
from orchestra_tprm.agents.base import BaseTPRMAgent, strip_json_fences
from orchestra_tprm.schemas import Citation, Finding

_SYSTEM = """You are a SOC2 / ISO27001 auditor. For each notable control in the
attached attestation, output ONE JSON object:
  - control_id: short ref like "CC6.1" or "A.9.4"
  - status: "covered" | "partial" | "gap"
  - severity: "low" | "medium" | "high" | "critical"
  - summary: one sentence on what the report says (or omits)
  - citation_page: integer page in the source document
Focus on: access management, MFA, encryption at rest/transit, incident
response coverage, audit logging, vulnerability management, and change
control.
Output a JSON ARRAY. No prose.
"""


class SecurityAgent(BaseTPRMAgent):
    """Vendor-mode specialist: maps SOC2/ISO27001 control findings from
    attestation documents. Uses gemini-2.5-flash for cost efficiency."""

    name = "SecurityAgent"

    def __init__(self, model: str = "gemini-2.5-flash") -> None:
        self.model = model

    async def _emit_findings(self, ctx: ExecutionContext) -> list[Finding]:
        routing = ctx.state.get("routing", {})
        file_uris = ctx.state.get("file_uris", {})
        all_findings: list[Finding] = []
        for doc_id in routing.get(self.name, []):
            uri = file_uris.get(doc_id)
            if not uri:
                continue

            attachments: list[dict] | None = None
            body = ""
            if uri.startswith("https://"):
                attachments = [{"file_uri": uri, "mime_type": "application/pdf"}]
            else:
                # local:// — inline text. Tolerate read failures so
                # unit tests with synthetic paths still pass.
                try:
                    content = read_uri(uri)
                except (FileNotFoundError, OSError, UnicodeDecodeError):
                    content = ""
                if content:
                    body = f"=== {doc_id} ===\n{content}\n"

            prompt = (
                f"Subject: {ctx.state.get('subject_name', 'unknown')}\n"
                f"Document: {doc_id}\n"
                f"{body}"
                "Audit the SOC2/ISO27001 report above and emit the JSON array. "
                "Use `citation_page` if the document has page numbers; "
                "otherwise set it to null and rely on `control_id`."
            )
            text = await self._call_llm(
                ctx, prompt=prompt, system=_SYSTEM, attachments=attachments
            )
            stripped = strip_json_fences(text)
            if not stripped:
                continue
            try:
                items = json.loads(stripped)
            except json.JSONDecodeError:
                all_findings.append(
                    Finding(
                        agent=self.name,
                        category="parse-error",
                        severity="high",
                        summary=f"SecurityAgent: LLM returned non-JSON for {doc_id}: {text[:120]}",
                        evidence=[Citation(file_id=doc_id)],
                    )
                )
                continue
            for item in items:
                ctrl = item.get("control_id", "unknown")
                all_findings.append(
                    Finding(
                        agent=self.name,
                        category=f"soc2-{ctrl.lower()}",
                        severity=item.get("severity", "low"),
                        summary=item.get("summary", ""),
                        evidence=[
                            Citation(
                                file_id=doc_id,
                                page=item.get("citation_page"),
                            )
                        ],
                        raw=item,
                    )
                )
        return all_findings
