"""CodeAgent — tech-debt and license risk from source code / repo metadata.

Sends repository metadata or source code snippets to the LLM and receives a
single structured assessment covering tech debt, license exposure, and whether
a security patch is needed. Returns exactly one Finding per invocation.
"""
from __future__ import annotations

import json

from orchestra.core.context import ExecutionContext

from orchestra_tprm.agents._uri import read_uri
from orchestra_tprm.agents.base import BaseTPRMAgent
from orchestra_tprm.schemas import Finding

_SYSTEM = """You are a software supply-chain security analyst.
Analyse the source code or repository metadata provided and return a single JSON object:
  - summary: one sentence describing the overall code health / risk
  - tech_debt: "low" | "medium" | "high"
  - license: SPDX identifier string, or null if unknown
  - patch_needed: true if a known CVE or critical vulnerability requires an urgent patch
Output ONLY the JSON object. No prose, no Markdown fences.
"""


def _tech_debt_to_severity(tech_debt: str) -> str:
    """Map tech_debt value to a Finding severity string."""
    mapping = {"low": "low", "medium": "medium", "high": "high"}
    return mapping.get(tech_debt, "medium")


class CodeAgent(BaseTPRMAgent):
    """Vendor-mode specialist: assesses source code / repository metadata for
    tech-debt, license risk, and patch urgency.

    Reads document URIs from ``ctx.state["routing"]["CodeAgent"]`` resolved
    via ``ctx.state["file_uris"]``. All documents are concatenated into one
    prompt; the LLM returns a single JSON object which becomes one Finding.
    """

    name = "CodeAgent"

    def __init__(self, model: str = "gemini-2.5-flash") -> None:
        self.model = model

    async def _emit_findings(self, ctx: ExecutionContext) -> list[Finding]:
        routing: dict = ctx.state.get("routing", {})
        file_uris: dict = ctx.state.get("file_uris", {})
        my_docs: list[str] = routing.get(self.name, [])

        # Collect URIs and attachment refs
        text_chunks: list[str] = []
        attachments: list[dict] = []

        for doc_id in my_docs:
            uri = file_uris.get(doc_id)
            if not uri:
                continue
            if uri.startswith("https://"):
                attachments.append({"file_uri": uri, "mime_type": "text/plain"})
            else:
                content = read_uri(uri)
                if content:
                    text_chunks.append(f"=== {doc_id} ===\n{content}")

        if not text_chunks and not attachments:
            return []

        body = "\n\n".join(text_chunks) if text_chunks else ""
        prompt = (
            f"Subject: {ctx.state.get('subject_name', 'unknown')}\n"
            f"Repository / source documents:\n{body}\n"
            "Assess the code health and emit the JSON object as instructed."
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
            data = json.loads(text)
        except json.JSONDecodeError:
            return [
                Finding(
                    agent=self.name,
                    category="parse-error",
                    severity="critical",
                    summary=f"CodeAgent: LLM returned non-JSON response: {text[:120]}",
                )
            ]

        if not isinstance(data, dict):
            return [
                Finding(
                    agent=self.name,
                    category="parse-error",
                    severity="critical",
                    summary=f"CodeAgent: expected JSON object, got {type(data).__name__}",
                )
            ]

        return [
            Finding(
                agent=self.name,
                category="code-risk",
                severity=_tech_debt_to_severity(data.get("tech_debt", "low")),
                summary=data.get("summary", ""),
                raw=data,
            )
        ]
