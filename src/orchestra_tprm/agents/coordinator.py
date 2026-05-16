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
from orchestra_tprm.schemas import Finding


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
        sections = _ma_sections_from_text(narrative)
        body = "\n\n".join(f"{h}\n{c}" for h, c in sections.items())

        if self._docs is None:
            return {
                "verdict_doc_id": self._doc_id,
                "verdict_local_path": "",
            }

        if self._doc_id:
            doc_id = self._doc_id
            self._docs.append_text(doc_id, body)
        else:
            title = f"Deal Memo — {state.get('subject_name', 'unknown')}"
            doc_id = self._docs.create_doc(title, body)

        return {
            "verdict_doc_id": doc_id,
            "verdict_local_path": f"doc://{doc_id}",
        }
