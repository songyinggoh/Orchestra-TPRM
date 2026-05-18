"""build_graph(mode_config, *, adapters, ...) -> CompiledGraph.

Per-mode wiring is fully declarative: the same pipeline shape
(``bootstrap -> intake -> router -> [specialists in parallel] -> policy
-> coordinator -> END``) runs for both vendor and M&A; mode-specific
behaviour is driven by ``ModeConfig`` (specialist models, output_kind,
coordinator_template, code_agent_generates_patch).  Any specialist whose
model is ``None`` in the active config is simply not added to the
parallel fan-out -- "declarative skip".

The graph is composed entirely of ``AgentNode`` shims so each node
receives the ``ExecutionContext`` (and therefore the LLM provider);
``FunctionNode`` would only get the state dict.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from orchestra.core.agent import BaseAgent
from orchestra.core.context import ExecutionContext
from orchestra.core.graph import WorkflowGraph
from orchestra.core.nodes import AgentNode
from orchestra.core.types import END, AgentResult, LLMResponse, Message, MessageRole

from orchestra_tprm.agents.base import safe_specialist
from orchestra_tprm.agents.coordinator import Coordinator
from orchestra_tprm.agents.intake import intake_node
from orchestra_tprm.agents.pmi_planner import PMIPlannerAgent
from orchestra_tprm.agents.policy import PolicyAgent
from orchestra_tprm.agents.specialists.code import CodeAgent
from orchestra_tprm.agents.specialists.external import ExternalAgent
from orchestra_tprm.agents.remediation import RemediationAgent
from orchestra_tprm.agents.risk_score import RiskScoreAgent
from orchestra_tprm.agents.specialists.esg import ESGAgent
from orchestra_tprm.agents.specialists.legal import LegalAgent
from orchestra_tprm.agents.specialists.security import SecurityAgent
from orchestra_tprm.modes.config import ModeConfig
from orchestra_tprm.schemas import Finding, TPRMState

# FinancialAgent is M&A-only; imported lazily so vendor-only deployments
# don't need to ship its dependencies.
try:
    from orchestra_tprm.agents.specialists.financial import FinancialAgent
except ImportError:  # pragma: no cover
    FinancialAgent = None  # type: ignore[assignment]

try:
    from orchestra_tprm.agents.specialists.saas_metrics import SaaSMetricsAgent
except ImportError:  # pragma: no cover
    SaaSMetricsAgent = None  # type: ignore[assignment]


@dataclass
class Adapters:
    """Bundle of every adapter ``build_graph`` may need.

    Slots may be ``None`` when the active mode doesn't use them
    (e.g. ``docs=None`` for vendor, ``sheets=None`` for M&A).
    """

    drive: Any
    files: Any
    sheets: Any
    docs: Any
    bq: Any
    github: Any


# ---------------------------------------------------------------------------
# Internal adapter shims -- DO NOT TOUCH existing Fake* classes per the
# Task 28 constraints, so we translate to the Protocol surface here.
# ---------------------------------------------------------------------------


class _BQShim:
    """Translate ``append_findings`` (the PolicyAgent Protocol) onto whichever
    underlying BQ-shaped adapter the caller supplied.

    Supports both modern adapters (with native ``append_findings``) and the
    legacy ``FakeBigQueryAdapter`` (``insert_rows`` only).
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def append_findings(
        self,
        dataset: str,
        table: str,
        run_id: str,
        findings: list[Finding],
        *,
        mode: str = "",
        subject: str = "",
    ) -> int:
        native = getattr(self._inner, "append_findings", None)
        if native is not None:
            return await native(dataset, table, run_id, findings, mode=mode, subject=subject)
        rows = [
            {
                "run_id": run_id,
                "agent": f.agent,
                "category": f.category,
                "severity": f.severity,
                "summary": f.summary,
                "evidence": json.dumps([c.model_dump() for c in f.evidence]),
                "raw": json.dumps(f.raw),
            }
            for f in findings
        ]
        legacy_insert = getattr(self._inner, "insert_rows", None)
        if legacy_insert is not None:
            legacy_insert(dataset, table, rows)
            return len(rows)
        raise TypeError(
            f"BQ adapter {type(self._inner).__name__!r} has neither "
            "'append_findings' nor 'insert_rows' — no findings were written."
        )


# ---------------------------------------------------------------------------
# Specialist factory -- maps the canonical lowercase ID used in
# ``ModeConfig.specialists`` to the BaseTPRMAgent runtime instance plus its
# ``.name`` attribute (which is the key used in ``state["routing"]``).
# ---------------------------------------------------------------------------


def _build_specialists(cfg: ModeConfig, adapters: Adapters) -> dict[str, Any]:
    """Return ``{cfg_key: agent_instance}`` for every active specialist."""
    spec = cfg.specialists
    active: dict[str, Any] = {}
    if spec.legal:
        active["legal"] = LegalAgent(model=spec.legal)
    if spec.security:
        active["security"] = SecurityAgent(model=spec.security)
    if spec.external:
        active["external"] = ExternalAgent(model=spec.external)
    if spec.code:
        active["code"] = CodeAgent(model=spec.code)
    if spec.financial and FinancialAgent is not None:
        active["financial"] = FinancialAgent(model=spec.financial)
    if spec.saas_metrics and SaaSMetricsAgent is not None:
        active["saas_metrics"] = SaaSMetricsAgent(model=spec.saas_metrics)
    if spec.esg:
        active["esg"] = ESGAgent(model=spec.esg)
    return active


# ---------------------------------------------------------------------------
# Bootstrap node -- seeds ``github_url`` into state and runs intake.
# ---------------------------------------------------------------------------


async def _bootstrap(state: dict[str, Any], *, github_url: str) -> dict[str, Any]:
    return {"github_url": github_url}


async def _run_intake(
    state: dict[str, Any],
    *,
    drive: Any,
    drive_folder_id: str,
) -> dict[str, Any]:
    """Resolve the packet manifest from EITHER a local manifest.yaml OR a
    seeded Drive folder, then re-key ``file_uris`` by filename so
    downstream specialists can read ``file_uris[<filename>]`` directly
    (matching ``routing[<AgentName>][i]``).
    """
    from pathlib import Path

    pkt = Path(state.get("packet_path", ""))
    manifest: list[dict[str, Any]]
    file_uris: dict[str, str] = {}

    if pkt.is_dir() and (pkt / "manifest.yaml").exists():
        # Local packet path
        update = await intake_node(state)
        manifest = list(update.get("packet_manifest", []))
        file_uris.update(update.get("file_uris", {}))
        subject_name = update.get("subject_name", state.get("subject_name", ""))
    elif drive is not None and drive_folder_id:
        # Drive-backed packet (e.g. FakeDriveAdapter seeded by integration tests).
        # Materialise each file under a temp dir as ``local://`` so specialists
        # using ``read_uri`` get real bytes to feed the LLM prompt.
        import tempfile

        files = drive.list_files(drive_folder_id) or []
        materialised_root = Path(tempfile.mkdtemp(prefix="orch_tprm_drive_"))
        manifest = []
        for f in files:
            name = f.get("name") or f.get("id") or ""
            kind = f.get("kind") or _infer_kind(name)
            file_id = f.get("id", name)
            content = b""
            download = getattr(drive, "download_file", None)
            if callable(download):
                try:
                    content = download(file_id) or b""
                except Exception:
                    content = b""
            local_path = materialised_root / name
            local_path.write_bytes(content)
            uri = f"local://{local_path.as_posix()}"
            manifest.append({"path": name, "kind": kind, "file_uri": uri})
            # Index by filename, not by kind (CR-07: multiple files of the same
            # kind — e.g. two contracts — would overwrite each other when keyed
            # by kind; the subsequent filename-keying loop at the end covers lookup).
            file_uris[name] = uri
        subject_name = state.get("subject_name", "")
    else:
        return {"packet_manifest": [], "file_uris": {}}

    # Add filename keys alongside kind keys so specialists resolve URIs
    # directly from ``routing[<AgentName>][i]`` which holds filenames.
    for entry in manifest:
        name = entry["path"].split("/")[-1].split("\\")[-1]
        file_uris[name] = entry["file_uri"]

    return {
        "packet_manifest": manifest,
        "file_uris": file_uris,
        "subject_name": subject_name,
    }


def _infer_kind(filename: str) -> str:
    lower = filename.lower()
    if "msa" in lower or "contract" in lower or "agreement" in lower:
        return "contract"
    if "soc2" in lower or "iso" in lower:
        return "security_attestation"
    if "10-k" in lower or "10k" in lower or "annual" in lower:
        return "annual_report"
    if "financial" in lower:
        return "financial_filing"
    return "unknown"


# ---------------------------------------------------------------------------
# Router agent -- LLM-driven document-to-specialist assignment.
# ---------------------------------------------------------------------------


class _DocRouter(BaseAgent):
    """LLM-driven router: classifies each document in ``packet_manifest``
    and assigns it to one or more specialists by *name*.

    Output: ``state["routing"] = {AgentName: [filename, ...]}``.  AgentName
    matches each specialist's class-attribute ``name`` (e.g.
    ``"LegalAgent"``) so existing specialists pick it up via
    ``routing.get(self.name, [])`` without any rewiring.
    """

    name: str = "DocRouterAgent"
    active_specialist_names: list[str] = []
    model: str = "gemini-2.5-flash"

    async def run(self, input: Any, context: ExecutionContext) -> AgentResult:  # type: ignore[override]
        state = input if isinstance(input, dict) else (context.state or {})
        manifest = state.get("packet_manifest", []) or []
        subject = state.get("subject_name", "unknown")
        active = ", ".join(self.active_specialist_names)
        docs_block = "\n".join(
            f"- {entry.get('path', '?').split('/')[-1].split('\\')[-1]}"
            f" (kind={entry.get('kind', 'unknown')})"
            for entry in manifest
        )
        system = (
            "You are a TPRM document router. For each document, decide "
            f"which of these specialists should review it: [{active}]. "
            "Output a JSON array of objects {{\"doc\": <filename>, "
            "\"specialists\": [<AgentName>, ...]}}. No prose."
        )
        user = (
            f"Subject: {subject}\nDocuments:\n{docs_block}\n"
            "Return the JSON array."
        )

        if context.provider is None:
            routing = _classify_no_llm(manifest, self.active_specialist_names)
            return AgentResult(
                agent_name=self.name,
                state_updates={"routing": routing},
            )

        resp: LLMResponse = await context.provider.complete(
            [
                Message(role=MessageRole.SYSTEM, content=system),
                Message(role=MessageRole.USER, content=user),
            ],
            model=self.model,
        )
        text = (resp.content or "").strip()
        # Permissive JSON extraction -- handle fenced output etc.
        match = re.search(r"\[.*\]", text, re.DOTALL)
        items: list[dict[str, Any]] = []
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list):
                    items = [i for i in parsed if isinstance(i, dict)]
            except json.JSONDecodeError:
                items = []

        if not items:
            # LLM produced nothing usable -- fall back to kind-based
            # classification so the rest of the graph still runs.
            routing = _classify_no_llm(manifest, self.active_specialist_names)
        else:
            routing = {n: [] for n in self.active_specialist_names}
            for item in items:
                doc = str(item.get("doc", ""))
                specs = item.get("specialists", []) or []
                for s in specs:
                    if s in routing:
                        routing[s].append(doc)

        # Backstop: every active specialist must have at least one doc
        # assigned so the parallel fan-out remains balanced and every
        # specialist consumes its scripted LLM response. We assign the
        # first available doc to any unassigned specialist.
        if manifest:
            first_doc = manifest[0].get("path", "").split("/")[-1].split("\\")[-1]
            for spec_name, docs in routing.items():
                if not docs:
                    routing[spec_name] = [first_doc]

        return AgentResult(
            agent_name=self.name,
            state_updates={"routing": routing},
        )


_KIND_TO_AGENT_NAMES = {
    "contract": ["LegalAgent"],
    "security_attestation": ["SecurityAgent"],
    "financial_statement": ["FinancialAgent", "LegalAgent", "SaaSMetricsAgent"],
    "financial_filing": ["FinancialAgent", "LegalAgent", "SaaSMetricsAgent"],
    "source_code": ["CodeAgent"],
    "investor_deck": ["FinancialAgent", "SaaSMetricsAgent"],
    "annual_report": ["LegalAgent", "FinancialAgent", "SecurityAgent", "SaaSMetricsAgent", "ESGAgent"],
    "sustainability_report": ["ESGAgent"],
    "code_of_conduct": ["ESGAgent"],
    "diversity_report": ["ESGAgent"],
    "governance_disclosure": ["ESGAgent"],
    "unknown": ["LegalAgent", "SecurityAgent"],
}


def _classify_no_llm(
    manifest: list[dict[str, Any]],
    active: list[str],
) -> dict[str, list[str]]:
    routing: dict[str, list[str]] = {a: [] for a in active}
    for entry in manifest:
        kind = entry.get("kind", "unknown")
        name = entry.get("path", "?").split("/")[-1].split("\\")[-1]
        for agent_name in _KIND_TO_AGENT_NAMES.get(kind, ["LegalAgent", "SecurityAgent"]):
            if agent_name in routing:
                routing[agent_name].append(name)
    return routing


# ---------------------------------------------------------------------------
# VDR Completeness Gate -- M&A-mode pre-flight check.
# Categorises each document in packet_manifest against the standard DRL
# (Document Request List) categories and emits informational findings for
# missing categories. Does NOT block the run -- always returns a state
# patch that prepends warning findings.
# ---------------------------------------------------------------------------

_DRL_CATEGORIES = (
    "financial_statements",
    "legal_corporate",
    "ip_assignments",
    "security_pentest",
    "cap_table",
    "tax_returns",
)

_DRL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "financial_statements": ("financial", "10-k", "10k", "income", "balance-sheet", "p&l", "annual"),
    "legal_corporate":      ("articles", "bylaws", "incorporation", "corporate", "minutes", "consent"),
    "ip_assignments":       ("ip-assignment", "ip_assignment", "patent", "trademark", "copyright", "invention"),
    "security_pentest":     ("pentest", "pen-test", "penetration", "soc2", "soc-2", "iso27001", "iso-27001"),
    "cap_table":            ("cap-table", "captable", "cap_table", "shareholder", "equity-grant", "option-grant"),
    "tax_returns":          ("tax-return", "tax_return", "1120", "k-1", "form-1120", "irs"),
}


def _vdr_completeness_check(manifest: list[dict[str, Any]]) -> list[Finding]:
    """Return informational Findings for missing DRL categories.

    Each manifest entry's `path` and `kind` fields are matched (case-insensitive
    substring) against the keyword table above. Missing categories produce one
    Finding each with severity='low', workstream='legal', ic_decision='post-close-monitoring'.
    """
    present: set[str] = set()
    for entry in manifest:
        path = str(entry.get("path", "")).lower()
        kind = str(entry.get("kind", "")).lower()
        haystack = f"{path}|{kind}"
        for category, keywords in _DRL_KEYWORDS.items():
            if any(kw in haystack for kw in keywords):
                present.add(category)

    missing = [c for c in _DRL_CATEGORIES if c not in present]
    findings: list[Finding] = []
    for category in missing:
        findings.append(
            Finding(
                agent="VDRGate",
                category=f"vdr-missing-{category.replace('_', '-')}",
                severity="low",
                summary=(
                    f"VDR completeness gate: missing document category "
                    f"'{category}' -- monitor post-close for follow-up requests."
                ),
                workstream="legal",
                ic_decision="post-close-monitoring",
            )
        )
    return findings


def _make_vdr_gate_shim() -> BaseAgent:
    class _VDRGateShim(BaseAgent):
        name: str = "VDRGate"

        async def run(self, input: Any, context: ExecutionContext) -> AgentResult:  # type: ignore[override]
            state = input if isinstance(input, dict) else (context.state or {})
            manifest = state.get("packet_manifest", []) or []
            missing = _vdr_completeness_check(manifest)
            return AgentResult(
                agent_name=self.name,
                state_updates={
                    "findings": [f.model_dump() for f in missing]
                },
            )

    return _VDRGateShim()


# ---------------------------------------------------------------------------
# Specialist shim -- wraps a BaseTPRMAgent so it conforms to BaseAgent.run.
# ---------------------------------------------------------------------------


def _make_spec_shim(specialist: Any) -> BaseAgent:
    """Wrap a BaseTPRMAgent into a BaseAgent shim.

    The shim's ``run(input, context)`` injects the latest ``state_dict``
    (passed by AgentNode's input_mapper) into ``context.state`` so the
    underlying specialist sees the post-router routing dict even when
    running inside a parallel fan-out (parallel branches clone the parent
    context at the time of the fan-out edge, which is BEFORE the router's
    state update has been applied to ``context.state``).
    """
    wrapped = safe_specialist(specialist)
    spec_name = specialist.name

    class _SpecShim(BaseAgent):
        name: str = spec_name
        model: str | None = getattr(specialist, "model", None)

        async def run(self, input: Any, context: ExecutionContext) -> AgentResult:  # type: ignore[override]
            if isinstance(input, dict):
                context.state = input
            findings = await wrapped(context)
            return AgentResult(
                agent_name=self.name,
                state_updates={
                    "findings": [
                        f.model_dump() if hasattr(f, "model_dump") else f
                        for f in findings
                    ]
                },
            )

    return _SpecShim()


# ---------------------------------------------------------------------------
# Policy & Coordinator shims (need ``ctx``, so they can't be FunctionNodes).
# ---------------------------------------------------------------------------


def _make_policy_shim(policy: PolicyAgent) -> BaseAgent:
    class _PolicyShim(BaseAgent):
        name: str = "PolicyAgent"

        async def run(self, input: Any, context: ExecutionContext) -> AgentResult:  # type: ignore[override]
            state = input if isinstance(input, dict) else (context.state or {})
            update = await policy(state, ctx=context)
            return AgentResult(agent_name=self.name, state_updates=update)

    return _PolicyShim()


def _make_coordinator_shim(coord: Coordinator) -> BaseAgent:
    class _CoordShim(BaseAgent):
        name: str = "Coordinator"

        async def run(self, input: Any, context: ExecutionContext) -> AgentResult:  # type: ignore[override]
            state = input if isinstance(input, dict) else (context.state or {})
            update = await coord(state, ctx=context)
            return AgentResult(agent_name=self.name, state_updates=update)

    return _CoordShim()


def _make_pmi_planner_shim(planner: PMIPlannerAgent) -> BaseAgent:
    class _PMIPlannerShim(BaseAgent):
        name: str = "PMIPlannerAgent"

        async def run(self, input: Any, context: ExecutionContext) -> AgentResult:  # type: ignore[override]
            state = input if isinstance(input, dict) else (context.state or {})
            update = await planner(state, ctx=context)
            return AgentResult(agent_name=self.name, state_updates=update)

    return _PMIPlannerShim()


def _make_risk_score_shim(agent: RiskScoreAgent) -> BaseAgent:
    class _RiskScoreShim(BaseAgent):
        name: str = "RiskScoreAgent"

        async def run(self, input: Any, context: ExecutionContext) -> AgentResult:  # type: ignore[override]
            state = input if isinstance(input, dict) else (context.state or {})
            update = await agent(state, ctx=context)
            return AgentResult(agent_name=self.name, state_updates=update)

    return _RiskScoreShim()


def _make_remediation_shim(agent: RemediationAgent) -> BaseAgent:
    class _RemediationShim(BaseAgent):
        name: str = "RemediationAgent"

        async def run(self, input: Any, context: ExecutionContext) -> AgentResult:  # type: ignore[override]
            state = input if isinstance(input, dict) else (context.state or {})
            update = await agent(state, ctx=context)
            return AgentResult(agent_name=self.name, state_updates=update)

    return _RemediationShim()


# ---------------------------------------------------------------------------
# Bootstrap shim (also needs nothing from ctx but kept as an AgentNode for
# uniformity and to expose ``output_key="github_url"`` for invariant W-1).
# ---------------------------------------------------------------------------


def _make_bootstrap_shim(github_url: str) -> BaseAgent:
    class _BootstrapShim(BaseAgent):
        name: str = "BootstrapAgent"

        async def run(self, input: Any, context: ExecutionContext) -> AgentResult:  # type: ignore[override]
            return AgentResult(
                agent_name=self.name,
                state_updates={"github_url": github_url},
            )

    return _BootstrapShim()


def _make_intake_shim(*, drive: Any, drive_folder_id: str) -> BaseAgent:
    captured_drive = drive
    captured_folder = drive_folder_id

    class _IntakeShim(BaseAgent):
        name: str = "IntakeAgent"

        async def run(self, input: Any, context: ExecutionContext) -> AgentResult:  # type: ignore[override]
            state = input if isinstance(input, dict) else (context.state or {})
            update = await _run_intake(
                state,
                drive=captured_drive,
                drive_folder_id=captured_folder,
            )
            return AgentResult(agent_name=self.name, state_updates=update)

    return _IntakeShim()


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def build_graph(
    cfg: ModeConfig,
    *,
    adapters: Adapters,
    drive_folder_id: str = "",
    sheet_id: str = "",
    doc_id: str = "",
    bq_dataset: str = "tprm_audit",
    bq_table: str = "tprm_findings",
    github_url: str = "",
) -> Any:
    """Build the per-mode TPRM workflow graph and return a CompiledGraph.

    The same pipeline shape applies to both modes; ``cfg`` controls which
    specialists run and which Coordinator output_kind ("sheet" | "doc")
    is dispatched.
    """
    g = WorkflowGraph(state_schema=TPRMState)

    # --- Build runtime objects ---
    specialists = _build_specialists(cfg, adapters)
    active_specialist_names = [a.name for a in specialists.values()]

    bq_shim = _BQShim(adapters.bq)
    policy = PolicyAgent(
        mode_config=cfg, bq=bq_shim, dataset=bq_dataset, table=bq_table
    )
    # RiskScoreAgent reuses the same policy YAML as PolicyAgent (weights +
    # risk_score_thresholds). Load it once here so the agent gets the data
    # without re-parsing.
    import yaml as _yaml_for_risk
    from pathlib import Path as _Path_for_risk
    _policy_data = _yaml_for_risk.safe_load(
        _Path_for_risk(cfg.policy_pack).read_text(encoding="utf-8")
    )
    risk_score_agent = RiskScoreAgent(policy=_policy_data, model=cfg.policy_model)
    remediation_agent = RemediationAgent(mode=cfg.name, model=cfg.policy_model)
    coordinator = Coordinator(
        mode_config=cfg,
        sheets=adapters.sheets,
        docs=adapters.docs,
        sheet_id=sheet_id,
        doc_id=doc_id,
    )

    router_agent = _DocRouter(
        active_specialist_names=active_specialist_names,
        model=cfg.router_model,
    )

    # --- Wire nodes -------------------------------------------------------
    g.add_node(
        "bootstrap",
        AgentNode(
            agent=_make_bootstrap_shim(github_url),
            map_output=True,
            input_mapper=lambda s: s,
        ),
        output_key="github_url",
    )
    g.add_node(
        "intake",
        AgentNode(
            agent=_make_intake_shim(
                drive=adapters.drive,
                drive_folder_id=drive_folder_id,
            ),
            map_output=True,
            input_mapper=lambda s: s,
        ),
        output_key="packet_manifest",
    )
    g.add_node(
        "router",
        AgentNode(
            agent=router_agent,
            map_output=True,
            input_mapper=lambda s: s,
        ),
        output_key="routing",
    )

    specialist_node_ids: list[str] = []
    for cfg_key, specialist in specialists.items():
        node_id = cfg_key
        g.add_node(
            node_id,
            AgentNode(
                agent=_make_spec_shim(specialist),
                map_output=True,
                input_mapper=lambda s: s,
            ),
            output_key="findings",
        )
        specialist_node_ids.append(node_id)

    g.add_node(
        "risk_score",
        AgentNode(
            agent=_make_risk_score_shim(risk_score_agent),
            map_output=True,
            input_mapper=lambda s: s,
        ),
        output_key="risk_assessment",
    )
    g.add_node(
        "policy",
        AgentNode(
            agent=_make_policy_shim(policy),
            map_output=True,
            input_mapper=lambda s: s,
        ),
        output_key="policy_verdict",
    )
    g.add_node(
        "remediation",
        AgentNode(
            agent=_make_remediation_shim(remediation_agent),
            map_output=True,
            input_mapper=lambda s: s,
        ),
        output_key="remediation_plan",
    )
    g.add_node(
        "coordinator",
        AgentNode(
            agent=_make_coordinator_shim(coordinator),
            map_output=True,
            input_mapper=lambda s: s,
        ),
        output_key="verdict_local_path",
    )

    # --- Wire edges -------------------------------------------------------
    g.set_entry_point("bootstrap")
    g.add_edge("bootstrap", "intake")

    if cfg.output_kind == "doc":
        # M&A mode: insert VDR completeness gate between intake and router
        g.add_node(
            "vdr_gate",
            AgentNode(
                agent=_make_vdr_gate_shim(),
                map_output=True,
                input_mapper=lambda s: s,
            ),
            output_key="findings",
        )
        g.add_edge("intake", "vdr_gate")
        g.add_edge("vdr_gate", "router")
    else:
        g.add_edge("intake", "router")

    # Specialists fan out from router, join at risk_score (the new node).
    # risk_score then feeds into policy → remediation → coordinator.
    g.add_parallel("router", specialist_node_ids, join_node="risk_score")
    g.add_edge("risk_score", "policy")
    g.add_edge("policy", "remediation")
    g.add_edge("remediation", "coordinator")

    if cfg.output_kind == "doc":
        # M&A mode: PMI planner runs after coordinator
        pmi_planner = PMIPlannerAgent(model=cfg.coordinator_model)
        g.add_node(
            "pmi_planner",
            AgentNode(
                agent=_make_pmi_planner_shim(pmi_planner),
                map_output=True,
                input_mapper=lambda s: s,
            ),
            output_key="pmi_plan",
        )
        g.add_edge("coordinator", "pmi_planner")
        g.add_edge("pmi_planner", END)
    else:
        g.add_edge("coordinator", END)

    return g.compile()
