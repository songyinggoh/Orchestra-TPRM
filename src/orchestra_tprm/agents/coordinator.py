"""Coordinator — synthesises the verdict document via mode-specific template.

Mode dispatch is data-driven via ``ModeConfig.output_kind`` ("sheet" | "doc").
No mode-name string-literal branches appear in this module.

* ``output_kind == "sheet"`` (vendor): appends one row to a Sheets adapter
  AND mirrors the full sheet to a local CSV so callers running ``--local``
  can inspect the verdict without the Google API.
* ``output_kind == "doc"``  (M&A):    creates (or appends to) a Docs adapter
  with deal-memo sections, returning ``verdict_doc_id``.
"""
from __future__ import annotations

import csv
import io
import json
import tempfile
from pathlib import Path
from typing import Any

from orchestra.core.context import ExecutionContext
from orchestra.core.types import Message, MessageRole

from orchestra_tprm.agents.base import strip_json_fences
from orchestra_tprm.modes.config import ModeConfig
from orchestra_tprm.schemas import Finding, ICMemo, PMIPlan


def _ma_sections_from_text(text: str) -> dict[str, str]:
    """Parse the M&A coordinator LLM output into ``{heading: body}``.

    Accepts either a JSON object (preferred) or a free-text fallback in
    which case the entire body becomes the Executive Summary.
    """
    raw = strip_json_fences((text or "").strip())
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            pass
    return {"Executive Summary": raw}


def _render_workstream_section(workstream: str, findings: list[Finding]) -> str:
    """Render one workstream's findings block: counts by IC decision + top 3 details."""
    by_ic: dict[str, int] = {}
    for f in findings:
        key = f.ic_decision or "unclassified"
        by_ic[key] = by_ic.get(key, 0) + 1

    counts_line = ", ".join(
        f"{label}: {count}"
        for label, count in sorted(by_ic.items())
    ) or "no IC-classified findings"

    # Top 3 by severity (critical > high > medium > low)
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    top = sorted(findings, key=lambda f: sev_order.get(f.severity, 99))[:3]
    details_lines = []
    for f in top:
        exposure = ""
        if f.exposure_usd_range is not None:
            exposure = f" (exposure ${f.exposure_usd_range[0]:,}–${f.exposure_usd_range[1]:,})"
        details_lines.append(
            f"  - [{f.severity.upper()}] {f.category}: {f.summary}{exposure}"
        )

    details = "\n".join(details_lines) if details_lines else "  - (none)"
    return (
        f"Workstream: {workstream.title()}\n"
        f"Findings ({len(findings)}): {counts_line}\n"
        f"Top issues:\n{details}"
    )


def _render_risk_register(ic_memo: ICMemo | None) -> str:
    """Render the IC memo risk register as a simple text table."""
    if ic_memo is None or not ic_memo.risk_register:
        return "No risks registered."
    lines = [
        "Finding ID | Workstream | Exposure (USD) | Mitigation | Probability",
        "---------- | ---------- | -------------- | ---------- | -----------",
    ]
    for item in ic_memo.risk_register:
        exposure = "—"
        if item.exposure_usd_range is not None:
            exposure = f"${item.exposure_usd_range[0]:,}–${item.exposure_usd_range[1]:,}"
        lines.append(
            f"{item.finding_id} | {item.workstream} | {exposure} | "
            f"{item.mitigation} | {item.probability}"
        )
    return "\n".join(lines)


_PMI_TIER_ORDER = ("day-30", "day-60", "day-100", "day-180")


def _render_pmi_plan(pmi_plan: PMIPlan | None) -> str:
    """Render the PMI plan grouped by deadline tier."""
    if pmi_plan is None or not pmi_plan.items:
        return "No PMI actions planned."
    lines: list[str] = []
    if pmi_plan.summary:
        lines.append(pmi_plan.summary)
        lines.append("")
    for tier in _PMI_TIER_ORDER:
        tier_items = [it for it in pmi_plan.items if it.deadline_tier == tier]
        if not tier_items:
            continue
        lines.append(f"## {tier.upper()}")
        for it in tier_items:
            dep = f" (depends on: {it.dependency})" if it.dependency else ""
            lines.append(
                f"  - [{it.workstream}] {it.action} — owner: {it.owner}{dep}"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def _coerce_ic_memo(raw: Any) -> ICMemo | None:
    if raw is None:
        return None
    if isinstance(raw, ICMemo):
        return raw
    if isinstance(raw, dict):
        try:
            return ICMemo(**raw)
        except Exception:  # noqa: BLE001
            return None
    return None


def _coerce_pmi_plan(raw: Any) -> PMIPlan | None:
    if raw is None:
        return None
    if isinstance(raw, PMIPlan):
        return raw
    if isinstance(raw, dict):
        try:
            return PMIPlan(**raw)
        except Exception:  # noqa: BLE001
            return None
    return None


class Coordinator:
    """Mode-agnostic verdict writer.

    Behaviour is selected by ``mode_config.output_kind`` — no string-literal
    branching on the mode name happens here. Invariant (d) is asserted by
    ``tests/tprm/invariants/test_no_mode_branches.py``.
    """

    name = "Coordinator"

    def __init__(
        self,
        *,
        mode_config: ModeConfig,
        sheets: Any = None,
        docs: Any = None,
        sheet_id: str = "",
        doc_id: str = "",
        local_dir: Path | str | None = None,
    ) -> None:
        self._cfg = mode_config
        self._sheets = sheets
        self._docs = docs
        self._sheet_id = sheet_id
        self._doc_id = doc_id
        # Public attribute used by the invariant test (Task 24).
        self._template_path = mode_config.coordinator_template
        self._template = Path(self._template_path).read_text(encoding="utf-8")
        self._local_dir = (
            Path(local_dir)
            if local_dir is not None
            else Path(tempfile.gettempdir()) / "orchestra_tprm"
        )

    async def __call__(
        self,
        state: dict[str, Any],
        *,
        ctx: ExecutionContext | None = None,
    ) -> dict[str, Any]:
        findings: list[Finding] = [
            f if isinstance(f, Finding) else Finding(**f)
            for f in state.get("findings", [])
        ]
        prompt = self._template.format(
            subject=state.get("subject_name", "unknown"),
            verdict=state.get("policy_verdict", ""),
            score=state.get("risk_score", 0),
            findings_json=json.dumps(
                [f.model_dump() for f in findings], indent=2, default=str
            ),
        )
        narrative = ""
        if ctx is not None and getattr(ctx, "provider", None) is not None:
            msgs = [Message(role=MessageRole.USER, content=prompt)]
            resp = await ctx.provider.complete(
                msgs, model=self._cfg.coordinator_model
            )
            narrative = resp.content or ""

        dispatch = {
            "sheet": self._write_sheet,
            "doc": self._write_doc,
        }
        return await dispatch[self._cfg.output_kind](state, findings, narrative)

    # ------------------------------------------------------------------
    # Vendor mode: append-row to Sheets + mirror to local CSV
    # ------------------------------------------------------------------
    async def _write_sheet(
        self,
        state: dict[str, Any],
        findings: list[Finding],
        narrative: str,
    ) -> dict[str, Any]:
        row = {
            "subject": state.get("subject_name", ""),
            "policy_verdict": state.get("policy_verdict", ""),
            "risk_score": state.get("risk_score", 0),
            "categories": ",".join(f.category for f in findings),
            "narrative": narrative,
        }
        if self._sheets is not None and self._sheet_id:
            self._sheets.append_row(self._sheet_id, row)

        # Mirror every appended row to a local CSV so --local callers can
        # inspect the verdict without Google APIs.
        self._local_dir.mkdir(parents=True, exist_ok=True)
        csv_path = self._local_dir / f"{self._sheet_id or 'verdict'}.csv"
        rows = (
            self._sheets.read_rows(self._sheet_id)
            if self._sheets is not None and self._sheet_id
            else [row]
        )
        if rows:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for r in rows:
                writer.writerow({k: r.get(k, "") for k in rows[0].keys()})
            csv_path.write_text(buf.getvalue(), encoding="utf-8")
        else:
            csv_path.write_text("", encoding="utf-8")

        return {
            "verdict_doc_id": self._sheet_id,
            "verdict_local_path": f"file://{csv_path.as_posix()}",
        }

    # ------------------------------------------------------------------
    # M&A mode: create / append a deal-memo Doc
    # ------------------------------------------------------------------
    async def _write_doc(
        self,
        state: dict[str, Any],
        findings: list[Finding],
        narrative: str,
    ) -> dict[str, Any]:
        # 1. Executive Summary — parse the LLM narrative if it returned JSON sections,
        #    otherwise treat the whole narrative as the executive summary text.
        parsed_narrative = _ma_sections_from_text(narrative)
        executive_summary = (
            parsed_narrative.get("Executive Summary")
            or narrative
            or "(no narrative produced)"
        )

        # 2. Coerce IC memo and PMI plan defensively
        ic_memo = _coerce_ic_memo(state.get("ic_memo"))
        pmi_plan = _coerce_pmi_plan(state.get("pmi_plan"))

        # 3. Group findings by workstream
        ws_map: dict[str, list[Finding]] = {}
        for f in findings:
            key = f.workstream or "general"
            ws_map.setdefault(key, []).append(f)

        # 4. Build sections dict in the LOCKED order from CONTEXT.md.
        sections: dict[str, str] = {}
        sections["Executive Summary"] = executive_summary

        if ic_memo is not None:
            ic_lines = [
                f"Recommendation: {ic_memo.recommendation.upper()}",
                "",
                ic_memo.headline_terms or "(no headline terms)",
            ]
            if ic_memo.executive_summary:
                ic_lines.extend(["", ic_memo.executive_summary])
            sections["IC Memo"] = "\n".join(ic_lines)
        else:
            sections["IC Memo"] = "(no IC memo available — vendor-mode or missing MAScope)"

        # 3a. Workstream Reports (one per active workstream, alphabetical)
        workstream_block_lines: list[str] = []
        for ws in sorted(ws_map.keys()):
            workstream_block_lines.append(_render_workstream_section(ws, ws_map[ws]))
            workstream_block_lines.append("")
        sections["Workstream Reports"] = (
            "\n".join(workstream_block_lines).rstrip()
            or "(no workstream-tagged findings)"
        )

        # 4. Risk Register (sourced from IC memo)
        sections["Risk Register"] = _render_risk_register(ic_memo)

        # 5. PMI 100-Day Plan
        sections["PMI 100-Day Plan"] = _render_pmi_plan(pmi_plan)

        # 6. Appendix: Full Findings (machine-readable JSON dump)
        sections["Appendix: Full Findings"] = json.dumps(
            [f.model_dump() for f in findings], indent=2, default=str
        )

        # ----- Persist via DocsAdapter (or return early if no adapter) -----
        body = "\n\n".join(f"{h}\n{c}" for h, c in sections.items())

        if self._docs is None:
            return {
                "verdict_doc_id": self._doc_id,
                "verdict_local_path": "",
            }

        if self._doc_id:
            doc_id = self._doc_id
            self._docs.populate_ma_memo(doc_id, sections)
        else:
            title = f"Deal Memo — {state.get('subject_name', 'unknown')}"
            doc_id = self._docs.create_doc(title, body)

        return {
            "verdict_doc_id": doc_id,
            "verdict_local_path": f"doc://{doc_id}",
        }
