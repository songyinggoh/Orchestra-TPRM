"""CodeAgent — tech-debt and license risk from source code / repo metadata.

Sends repository metadata or source code snippets to the LLM and receives a
single structured assessment covering tech debt, license exposure, and whether
a security patch is needed. Returns exactly one Finding per invocation.
"""
from __future__ import annotations

import json

from orchestra.core.context import ExecutionContext

from orchestra_tprm.agents._uri import read_uri
from orchestra_tprm.agents.base import BaseTPRMAgent, strip_json_fences
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
    mapping = {"low": "low", "medium": "medium", "high": "high", "critical": "critical"}
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
                try:
                    content = read_uri(uri)
                except (FileNotFoundError, OSError, UnicodeDecodeError):
                    content = ""
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
            data = json.loads(strip_json_fences(text))
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

        sev = (
            "critical"
            if data.get("patch_needed")
            else _tech_debt_to_severity(data.get("tech_debt", "low"))
        )
        findings: list[Finding] = [
            Finding(
                agent=self.name,
                category="code-risk",
                severity=sev,
                summary=data.get("summary", ""),
                raw=data,
            )
        ]

        # ---- M&A-mode OSS license contamination pass (REQ-08) ----
        if ctx.state.get("mode") == "ma":
            license_str = str(data.get("license") or "").upper()

            ma_scope_raw = ctx.state.get("ma_scope")
            ev: int | None = None
            if isinstance(ma_scope_raw, dict):
                ev_raw = ma_scope_raw.get("enterprise_value_usd")
                ev = int(ev_raw) if ev_raw is not None else None
            elif ma_scope_raw is not None and hasattr(ma_scope_raw, "enterprise_value_usd"):
                ev = ma_scope_raw.enterprise_value_usd

            if license_str and ("AGPL" in license_str or ("GPL" in license_str and "LGPL" not in license_str)):
                findings.append(
                    Finding(
                        agent=self.name,
                        category="oss-license",
                        severity="critical",
                        summary=(
                            f"GPL/AGPL detected ({license_str}) in commercial product — "
                            "product may be unlicensable without source disclosure"
                        ),
                        workstream="tech",
                        ic_decision="deal-stopper",
                        exposure_usd_range=(0, ev) if ev else None,
                        raw={"license": license_str},
                    )
                )
            elif "LGPL" in license_str:
                findings.append(
                    Finding(
                        agent=self.name,
                        category="oss-license",
                        severity="high",
                        summary=(
                            f"LGPL detected ({license_str}) — ring-fence via specific "
                            "indemnity / warranty in SPA"
                        ),
                        workstream="tech",
                        ic_decision="SPA-protection",
                        raw={"license": license_str},
                    )
                )
            elif license_str and license_str not in {"MIT", "APACHE", "APACHE-2.0", "BSD", "BSD-3-CLAUSE", "BSD-2-CLAUSE", "ISC", ""}:
                findings.append(
                    Finding(
                        agent=self.name,
                        category="oss-license",
                        severity="low",
                        summary=(
                            f"Non-standard license ({license_str}) — monitor post-close "
                            "for contamination risk"
                        ),
                        workstream="tech",
                        ic_decision="post-close-monitoring",
                        raw={"license": license_str},
                    )
                )

        return findings
