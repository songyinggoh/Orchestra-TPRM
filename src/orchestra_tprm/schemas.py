"""Core schemas: Finding/Citation contract + typed workflow state."""
from __future__ import annotations

import uuid
from enum import IntEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field

from orchestra.core.state import WorkflowState, merge_list, merge_dict


class Severity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


SeverityLiteral = Literal["low", "medium", "high", "critical"]

_VALID_SEVERITIES = {"low", "medium", "high", "critical"}


def _coerce_severity(v: object) -> str:
    """Normalise LLM-returned severity strings before Pydantic validates the Literal."""
    s = str(v).lower() if v is not None else "medium"
    return s if s in _VALID_SEVERITIES else "medium"


_NormalizedSeverity = Annotated[SeverityLiteral, BeforeValidator(_coerce_severity)]


class Citation(BaseModel):
    file_id: str
    document_id: int | None = None
    page: int | None = None
    offset: int | None = None
    snippet: str = ""


class Finding(BaseModel):
    agent: str
    category: str
    severity: _NormalizedSeverity
    evidence: list[Citation] = Field(default_factory=list)
    summary: str
    raw: dict[str, Any] = Field(default_factory=dict)
    # M&A extensions (Phase 1)
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    exposure_usd_range: tuple[int, int] | None = None
    ic_decision: Literal["deal-stopper", "price-adjustment", "SPA-protection", "post-close-monitoring"] | None = None
    workstream: Literal["legal", "financial", "tech", "commercial", "hr", "esg", "regulatory"] | None = None


class MAScope(BaseModel):
    investment_thesis: str = ""
    enterprise_value_usd: int | None = None
    materiality_threshold_usd: int | None = None
    deal_breakers: list[str] = Field(default_factory=list)
    active_workstreams: list[str] = Field(default_factory=list)


class ICRiskItem(BaseModel):
    finding_id: str
    workstream: str
    exposure_usd_range: tuple[int, int] | None = None
    mitigation: Literal["price-chip", "indemnity", "escrow", "RWI", "earn-out", "CP", "post-close"]
    probability: Literal["low", "medium", "high"]


class ICMemo(BaseModel):
    executive_summary: str = ""
    headline_terms: str = ""
    recommendation: Literal["proceed", "reprice", "walk"] = "proceed"
    risk_register: list[ICRiskItem] = Field(default_factory=list)


class PMIItem(BaseModel):
    workstream: str
    action: str
    deadline_tier: Literal["day-30", "day-60", "day-100", "day-180"]
    owner: str
    dependency: str | None = None


class PMIPlan(BaseModel):
    summary: str = ""
    items: list[PMIItem] = Field(default_factory=list)


class TPRMState(WorkflowState):
    # Inputs
    mode: Literal["vendor", "ma"] = "vendor"
    subject_name: str = ""
    packet_path: str = ""
    github_url: str = ""

    # Intake outputs
    file_uris: Annotated[dict[str, str], merge_dict] = {}
    packet_manifest: Annotated[list[dict[str, Any]], merge_list] = []

    # Routing
    routing: Annotated[dict[str, list[str]], merge_dict] = {}

    # Per-specialist findings
    findings: Annotated[list[Finding], merge_list] = []

    # Policy outputs
    risk_score: float = 0.0
    policy_verdict: str = ""

    # Coordinator output
    verdict_doc_id: str = ""
    verdict_local_path: str = ""
    # M&A extensions (Phase 1)
    ma_scope: MAScope | None = None
    ic_memo: ICMemo | None = None
    pmi_plan: PMIPlan | None = None
