"""Core schemas: Finding/Citation contract + typed workflow state."""
from __future__ import annotations

from enum import IntEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from orchestra.core.state import WorkflowState, merge_list, merge_dict


class Severity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


SeverityLiteral = Literal["low", "medium", "high", "critical"]


class Citation(BaseModel):
    file_id: str
    document_id: int | None = None
    page: int | None = None
    offset: int | None = None
    snippet: str = ""


class Finding(BaseModel):
    agent: str
    category: str
    severity: SeverityLiteral
    evidence: list[Citation] = Field(default_factory=list)
    summary: str
    raw: dict[str, Any] = Field(default_factory=dict)


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
