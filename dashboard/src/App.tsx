import { useState, useEffect, useRef } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

type Mode = "vendor" | "ma";
type Phase = "idle" | "running" | "done" | "error";

interface Finding {
  agent: string;
  category: string;
  severity: "low" | "medium" | "high" | "critical";
  summary: string;
  evidence?: unknown[];
}

interface VerdictData {
  policy_verdict: string;
  risk_score: number;
  findings_count: number;
  findings: Finding[];
  verdict_doc_id?: string;
}

interface RunState {
  runId: string;
  phase: Phase;
  mode: Mode;
  subject: string;
  pipeline: string[];
  completedNodes: string[];
  nodeLabels: Record<string, string>;
  verdict: VerdictData | null;
  error: string | null;
  elapsedSec: number;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const VENDOR_PIPELINE = [
  "bootstrap_node", "intake_node", "router",
  "LegalAgent", "SecurityAgent", "ExternalAgent", "CodeAgent",
  "policy", "coordinator",
];
const MA_PIPELINE = [
  "bootstrap_node", "intake_node", "router",
  "LegalAgent", "SecurityAgent", "ExternalAgent", "CodeAgent", "FinancialAgent",
  "policy", "coordinator",
];
const NODE_LABELS: Record<string, string> = {
  bootstrap_node: "Bootstrap",
  intake_node: "Document Intake",
  router: "Document Router",
  LegalAgent: "Legal",
  SecurityAgent: "Security",
  ExternalAgent: "External Intel",
  CodeAgent: "Code Scan",
  FinancialAgent: "Financial",
  policy: "Policy Engine",
  coordinator: "Coordinator",
};

// MD3 Google-palette severity colors
const SEV_COLOR: Record<string, string> = {
  critical: "#ea4335",
  high:     "#fa7b17",
  medium:   "#fbbc04",
  low:      "#34a853",
};

// MD3 Google-palette verdict colors
const VERDICT_COLOR: Record<string, string> = {
  reject:      "#ea4335",
  conditional: "#fbbc04",
  approve:     "#34a853",
};

// Material Symbols icon name per verdict
const VERDICT_ICON: Record<string, string> = {
  approve:     "check_circle",
  conditional: "warning",
  reject:      "cancel",
};

// Material Symbols icon name per severity chip
const SEV_ICON: Record<string, string> = {
  critical: "dangerous",
  high:     "priority_high",
  medium:   "warning_amber",
  low:      "info",
};

// Specialist nodes that get left-indented
const SPECIALIST_NODES = new Set([
  "LegalAgent", "SecurityAgent", "ExternalAgent", "CodeAgent", "FinancialAgent",
]);

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDuration(sec: number): string {
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

function groupBySeverity(findings: Finding[]): Record<string, number> {
  const counts: Record<string, number> = { critical: 0, high: 0, medium: 0, low: 0 };
  for (const f of findings) counts[f.severity] = (counts[f.severity] ?? 0) + 1;
  return counts;
}

// ── PipelineStep ──────────────────────────────────────────────────────────────

function PipelineStep({
  node, label, done, active,
}: { node: string; label: string; done: boolean; active: boolean }) {
  const isSpecialist = SPECIALIST_NODES.has(node);

  // Derive styles from state
  let bgColor: string;
  let borderLeftColor: string;
  if (done) {
    bgColor = "rgba(26,115,232,0.12)";
    borderLeftColor = "var(--md-sys-color-primary)";
  } else if (active) {
    bgColor = "rgba(26,115,232,0.08)";
    borderLeftColor = "var(--md-sys-color-primary)";
  } else {
    bgColor = "transparent";
    borderLeftColor = "var(--md-sys-color-outline)";
  }

  // Icon element
  let iconEl: React.ReactNode;
  if (done) {
    iconEl = (
      // key forces remount → triggers step-check-in animation each time node completes
      <span
        key={`done-${node}`}
        className="material-symbols-outlined"
        style={{
          fontSize: 18,
          color: "var(--color-verdict-approve)",
          fontVariationSettings: "'FILL' 1, 'wght' 400",
          animation: "step-check-in 300ms cubic-bezier(0.2,0,0,1) forwards",
          flexShrink: 0,
        }}
      >
        check_circle
      </span>
    );
  } else if (active) {
    iconEl = (
      <span
        className="material-symbols-outlined pipeline-spin"
        style={{
          fontSize: 18,
          color: "var(--md-sys-color-primary)",
          fontVariationSettings: "'FILL' 0, 'wght' 400",
          flexShrink: 0,
        }}
      >
        autorenew
      </span>
    );
  } else {
    iconEl = (
      <span
        className="material-symbols-outlined"
        style={{
          fontSize: 18,
          color: "var(--md-sys-color-on-surface-variant)",
          fontVariationSettings: "'FILL' 0, 'wght' 400",
          opacity: 0.40,
          flexShrink: 0,
        }}
      >
        radio_button_unchecked
      </span>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--space-sm)",
        padding: "var(--space-sm2) var(--space-md)",
        background: bgColor,
        borderRadius: "var(--md-sys-shape-small)",
        borderLeft: `3px solid ${borderLeftColor}`,
        transition: "background 250ms ease, border-left-color 250ms ease",
        marginLeft: isSpecialist ? "var(--space-xl)" : 0,
      }}
    >
      {iconEl}
      <span
        style={{
          fontSize: 14,
          color: (done || active) ? "var(--md-sys-color-on-surface)" : "var(--md-sys-color-on-surface-variant)",
          fontWeight: (done || active) ? 500 : 400,
          lineHeight: 1.5,
        }}
      >
        {label}
      </span>
    </div>
  );
}

// ── SourceToggle ──────────────────────────────────────────────────────────────

function SourceToggle({
  value,
  onChange,
}: {
  value: "demo" | "drive";
  onChange: (v: "demo" | "drive") => void;
}) {
  const [hovered, setHovered] = useState<"demo" | "drive" | null>(null);

  const options: Array<{ id: "demo" | "drive"; label: string; icon: string }> = [
    { id: "demo",  label: "Demo Packet",  icon: "folder_special" },
    { id: "drive", label: "Google Drive", icon: "cloud" },
  ];

  return (
    <div
      style={{
        display: "flex",
        border: "1px solid var(--md-sys-color-outline)",
        borderRadius: "var(--md-sys-shape-small)",
        overflow: "hidden",
        height: 44,
      }}
    >
      {options.map((opt, idx) => {
        const isActive = value === opt.id;
        const isHovered = hovered === opt.id;

        let bg: string;
        let color: string;
        if (isActive) {
          bg = isHovered ? "#1765cc" : "var(--md-sys-color-primary)";
          color = "var(--md-sys-color-on-primary)";
        } else if (isHovered) {
          bg = "var(--md-sys-color-surface-container-high)";
          color = "var(--md-sys-color-on-surface)";
        } else {
          bg = "var(--md-sys-color-surface-container)";
          color = "var(--md-sys-color-on-surface-variant)";
        }

        return (
          <button
            key={opt.id}
            onClick={() => onChange(opt.id)}
            onMouseEnter={() => setHovered(opt.id)}
            onMouseLeave={() => setHovered(null)}
            style={{
              flex: 1,
              height: 44,
              fontSize: 14,
              fontWeight: 500,
              background: bg,
              color,
              border: "none",
              borderRadius: 0,
              borderRight: idx === 0 ? "1px solid var(--md-sys-color-outline)" : "none",
              cursor: "pointer",
              transition: "background 150ms ease, color 150ms ease",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "var(--space-xs)",
              padding: 0,
            }}
          >
            <span
              className="material-symbols-outlined"
              style={{
                fontSize: 18,
                fontVariationSettings: "'FILL' 0, 'wght' 400",
              }}
            >
              {opt.icon}
            </span>
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

// ── VerdictCard ───────────────────────────────────────────────────────────────

function VerdictCard({ data }: { data: VerdictData }) {
  const verdict = data.policy_verdict.toLowerCase();
  const color = VERDICT_COLOR[verdict] ?? "#8b8fa8";
  const sevCounts = groupBySeverity(data.findings);
  const verdictIcon = VERDICT_ICON[verdict] ?? "help";

  // FindingsTable hover state per row
  const [hoveredRow, setHoveredRow] = useState<number | null>(null);

  return (
    <div
      style={{
        background: "var(--md-sys-color-surface)",
        border: `1px solid ${color}4d`,
        borderRadius: "var(--md-sys-shape-large)",
        boxShadow: "var(--md-sys-elevation-2)",
        padding: "var(--space-xl)",
        animation: "verdict-reveal 350ms cubic-bezier(0.2,0,0,1) forwards",
      }}
    >
      {/* Header: badge + risk score + findings count */}
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-md)", marginBottom: "var(--space-lg)" }}>
        {/* Verdict badge */}
        <div
          style={{
            background: `${color}1a`,
            border: `1px solid ${color}4d`,
            borderRadius: "var(--md-sys-shape-small)",
            padding: "var(--space-sm) var(--space-md)",
            display: "flex",
            alignItems: "center",
            gap: "var(--space-xs)",
          }}
        >
          <span
            className="material-symbols-outlined"
            style={{
              fontSize: 18,
              color,
              fontVariationSettings: "'FILL' 1, 'wght' 400",
            }}
          >
            {verdictIcon}
          </span>
          <span
            style={{
              fontSize: 12,
              fontWeight: 500,
              color,
              textTransform: "uppercase",
              letterSpacing: "0.10em",
            }}
          >
            {data.policy_verdict}
          </span>
        </div>

        {/* Risk Score */}
        <div>
          <div style={{ fontSize: 28, fontWeight: 500, color: "var(--md-sys-color-on-surface)", lineHeight: 1.2 }}>
            {data.risk_score.toLocaleString()}
          </div>
          <div
            style={{
              fontSize: 12,
              fontWeight: 500,
              color: "var(--md-sys-color-on-surface-variant)",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
            }}
          >
            Risk Score
          </div>
        </div>

        {/* Findings count */}
        <div style={{ marginLeft: "auto", textAlign: "right" }}>
          <div style={{ fontSize: 28, fontWeight: 500, color: "var(--md-sys-color-on-surface)", lineHeight: 1.2 }}>
            {data.findings_count}
          </div>
          <div
            style={{
              fontSize: 12,
              fontWeight: 500,
              color: "var(--md-sys-color-on-surface-variant)",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
            }}
          >
            Findings
          </div>
        </div>
      </div>

      {/* Severity chips */}
      <div style={{ display: "flex", gap: "var(--space-sm)", marginBottom: "var(--space-lg)", flexWrap: "wrap" }}>
        {(["critical", "high", "medium", "low"] as const).map((sev) => {
          const c = SEV_COLOR[sev];
          const count = sevCounts[sev] ?? 0;
          return (
            <div
              key={sev}
              style={{
                background: `${c}1a`,
                border: `1px solid ${c}4d`,
                borderRadius: "var(--md-sys-shape-extra-small)",
                padding: "var(--space-xs) var(--space-sm)",
                display: "flex",
                alignItems: "center",
                gap: "var(--space-xs)",
                opacity: count === 0 ? 0.35 : 1,
              }}
            >
              <span
                className="material-symbols-outlined"
                style={{
                  fontSize: 14,
                  color: c,
                  fontVariationSettings: "'FILL' 1, 'wght' 400",
                }}
              >
                {SEV_ICON[sev]}
              </span>
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 500,
                  color: c,
                }}
              >
                {count} {sev}
              </span>
            </div>
          );
        })}
      </div>

      {/* Findings table */}
      {data.findings.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--md-sys-color-outline)" }}>
                {(["Agent", "Category", "Severity", "Summary"] as const).map((h) => (
                  <th
                    key={h}
                    style={{
                      textAlign: "left",
                      padding: "var(--space-sm) var(--space-sm2)",
                      color: "var(--md-sys-color-on-surface-variant)",
                      fontWeight: 500,
                      fontSize: 12,
                      textTransform: "uppercase",
                      letterSpacing: "0.06em",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.findings.slice(0, 50).map((f, i) => (
                <tr
                  key={i}
                  onMouseEnter={() => setHoveredRow(i)}
                  onMouseLeave={() => setHoveredRow(null)}
                  style={{
                    borderBottom: "1px solid var(--md-sys-color-outline-variant)",
                    background: hoveredRow === i ? "rgba(26,115,232,0.06)" : "transparent",
                    transition: "background 100ms ease",
                  }}
                >
                  <td
                    style={{
                      padding: "var(--space-sm) var(--space-sm2)",
                      color: "var(--md-sys-color-on-surface-variant)",
                      whiteSpace: "nowrap",
                      fontSize: 14,
                      fontWeight: 400,
                    }}
                  >
                    {f.agent}
                  </td>
                  <td
                    style={{
                      padding: "var(--space-sm) var(--space-sm2)",
                      color: "var(--md-sys-color-on-surface)",
                      whiteSpace: "nowrap",
                      fontSize: 14,
                      fontWeight: 400,
                    }}
                  >
                    {f.category}
                  </td>
                  <td style={{ padding: "var(--space-sm) var(--space-sm2)" }}>
                    <span
                      style={{
                        background: `${SEV_COLOR[f.severity] ?? "var(--md-sys-color-on-surface-variant)"}1a`,
                        color: SEV_COLOR[f.severity] ?? "var(--md-sys-color-on-surface-variant)",
                        fontWeight: 500,
                        fontSize: 12,
                        padding: "var(--space-xs) var(--space-sm)",
                        borderRadius: "var(--md-sys-shape-extra-small)",
                        textTransform: "uppercase",
                      }}
                    >
                      {f.severity}
                    </span>
                  </td>
                  <td
                    style={{
                      padding: "var(--space-sm) var(--space-sm2)",
                      color: "var(--md-sys-color-on-surface-variant)",
                      maxWidth: 400,
                      fontSize: 14,
                      fontWeight: 400,
                      lineHeight: 1.5,
                    }}
                  >
                    {f.summary}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.findings.length > 50 && (
            <p
              style={{
                color: "var(--md-sys-color-on-surface-variant)",
                fontSize: 12,
                fontWeight: 400,
                marginTop: "var(--space-sm)",
              }}
            >
              + {data.findings.length - 50} additional findings
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const [mode, setMode] = useState<Mode>("vendor");
  const [subjectName, setSubjectName] = useState("Acme Cloud Analytics");
  const [packetPath, setPacketPath] = useState("examples/tprm/acme");
  const [sourceType, setSourceType] = useState<"demo" | "drive">("demo");
  const [driveFolderUrl, setDriveFolderUrl] = useState("");
  const [runState, setRunState] = useState<RunState | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Hover state for "New Assessment" button in header
  const [newRunHovered, setNewRunHovered] = useState(false);
  // Hover/active states for Run Assessment button
  const [runBtnHovered, setRunBtnHovered] = useState(false);
  const [runBtnActive, setRunBtnActive] = useState(false);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    return () => {
      timerRef.current && clearInterval(timerRef.current);
      esRef.current?.close();
    };
  }, []);

  async function startRun() {
    setSubmitting(true);
    try {
      const res = await fetch("/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode,
          subject_name: subjectName,
          packet_path: sourceType === "demo" ? packetPath : "",
          drive_folder_url: sourceType === "drive" ? driveFolderUrl : undefined,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? "Server error");
      }
      const { run_id } = await res.json();

      const pipeline = mode === "ma" ? MA_PIPELINE : VENDOR_PIPELINE;

      const initialState: RunState = {
        runId: run_id,
        phase: "running",
        mode,
        subject: subjectName,
        pipeline,
        completedNodes: [],
        nodeLabels: { ...NODE_LABELS },
        verdict: null,
        error: null,
        elapsedSec: 0,
      };
      setRunState(initialState);

      // Elapsed timer
      const startTime = Date.now();
      timerRef.current = setInterval(() => {
        setRunState((prev) => prev ? {
          ...prev,
          elapsedSec: Math.floor((Date.now() - startTime) / 1000),
        } : prev);
      }, 1000);

      // SSE stream
      const es = new EventSource(`/events/${run_id}`);
      esRef.current = es;

      es.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          setRunState((prev) => {
            if (!prev) return prev;
            switch (msg.type) {
              case "node_done":
                return {
                  ...prev,
                  completedNodes: [...prev.completedNodes, msg.node],
                  nodeLabels: msg.label
                    ? { ...prev.nodeLabels, [msg.node]: msg.label }
                    : prev.nodeLabels,
                };
              case "verdict":
                return { ...prev, verdict: msg };
              case "done":
                timerRef.current && clearInterval(timerRef.current!);
                es.close();
                return { ...prev, phase: "done" };
              case "error":
                timerRef.current && clearInterval(timerRef.current!);
                es.close();
                return { ...prev, phase: "error", error: msg.message };
              default:
                return prev;
            }
          });
        } catch {}
      };

      es.onerror = () => {
        timerRef.current && clearInterval(timerRef.current!);
        setRunState((prev) => prev ? {
          ...prev, phase: "error", error: "Connection lost",
        } : prev);
        es.close();
      };
    } catch (err) {
      setRunState((prev) => prev
        ? { ...prev, phase: "error", error: String(err) }
        : {
            runId: "", phase: "error", mode, subject: subjectName,
            pipeline: [], completedNodes: [], nodeLabels: {}, verdict: null,
            error: String(err), elapsedSec: 0,
          }
      );
    } finally {
      setSubmitting(false);
    }
  }

  function reset() {
    timerRef.current && clearInterval(timerRef.current);
    esRef.current?.close();
    setRunState(null);
  }

  const rs = runState;

  // Derive Run Assessment button styles from interaction state
  const isRunDisabled = submitting || !subjectName || (sourceType === "demo" ? !packetPath : !driveFolderUrl);
  let runBtnBg = "var(--md-sys-color-primary)";
  let runBtnShadow = "var(--md-sys-elevation-2)";
  let runBtnScale = 1;
  if (!isRunDisabled) {
    if (runBtnActive) {
      runBtnBg = "#1557b0";
      runBtnShadow = "var(--md-sys-elevation-1)";
      runBtnScale = 0.99;
    } else if (runBtnHovered) {
      runBtnBg = "#1765cc";
      runBtnShadow = "var(--md-sys-elevation-3)";
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--md-sys-color-background)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* ── Header ── */}
      <header
        style={{
          height: 64,
          borderBottom: "1px solid var(--md-sys-color-outline)",
          padding: "0 var(--space-xl)",
          display: "flex",
          alignItems: "center",
          gap: "var(--space-md)",
          background: "var(--md-sys-color-surface)",
          boxShadow: "var(--md-sys-elevation-1)",
          flexShrink: 0,
        }}
      >
        {/* Logo */}
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: "var(--md-sys-shape-small)",
            background: "var(--md-sys-color-primary-container)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <span
            className="material-symbols-outlined"
            style={{
              fontSize: 22,
              color: "var(--md-sys-color-on-primary-container)",
              fontVariationSettings: "'FILL' 1, 'wght' 400",
            }}
          >
            account_tree
          </span>
        </div>

        {/* App name block */}
        <div>
          <div
            style={{
              fontWeight: 500,
              fontSize: 16,
              color: "var(--md-sys-color-on-surface)",
              lineHeight: 1.35,
            }}
          >
            Orchestra TPRM
          </div>
          <div
            style={{
              fontSize: 12,
              color: "var(--md-sys-color-on-surface-variant)",
              opacity: 0.45,
              lineHeight: 1.4,
            }}
          >
            Multi-Agent Risk Platform · Gemini 2.5 Flash
          </div>
        </div>

        {/* "New Assessment" button — shown in run view */}
        {rs && (
          <button
            onClick={reset}
            onMouseEnter={() => setNewRunHovered(true)}
            onMouseLeave={() => setNewRunHovered(false)}
            style={{
              marginLeft: "auto",
              background: newRunHovered ? "var(--md-sys-color-surface-container)" : "transparent",
              border: `1px solid ${newRunHovered ? "var(--md-sys-color-primary)" : "var(--md-sys-color-outline)"}`,
              color: newRunHovered ? "var(--md-sys-color-primary)" : "var(--md-sys-color-on-surface-variant)",
              padding: "var(--space-sm) var(--space-md)",
              borderRadius: "var(--md-sys-shape-small)",
              fontSize: 14,
              fontWeight: 500,
              display: "flex",
              alignItems: "center",
              gap: "var(--space-xs)",
              transition: "background 150ms ease, border-color 150ms ease, color 150ms ease",
            }}
          >
            <span
              className="material-symbols-outlined"
              style={{
                fontSize: 18,
                fontVariationSettings: "'FILL' 0, 'wght' 400",
              }}
            >
              arrow_back
            </span>
            New Assessment
          </button>
        )}
      </header>

      <main
        style={{
          flex: 1,
          padding: "var(--space-xl)",
          maxWidth: 1100,
          margin: "0 auto",
          width: "100%",
        }}
      >
        {!rs ? (
          /* ── New Assessment Form ── */
          <div
            style={{
              maxWidth: 520,
              margin: "var(--space-2xl) auto 0",
              background: "var(--md-sys-color-surface)",
              border: "1px solid var(--md-sys-color-outline)",
              borderRadius: "var(--md-sys-shape-large)",
              boxShadow: "var(--md-sys-elevation-2)",
              padding: "var(--space-xl)",
            }}
          >
            <h2
              style={{
                marginBottom: "var(--space-xs)",
                fontSize: 16,
                fontWeight: 500,
                color: "var(--md-sys-color-on-surface)",
              }}
            >
              New Assessment
            </h2>
            <p
              style={{
                color: "var(--md-sys-color-on-surface-variant)",
                marginBottom: "var(--space-xl)",
                fontSize: 14,
                fontWeight: 400,
                marginTop: 0,
              }}
            >
              Submit a vendor or M&A packet for multi-agent risk analysis.
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-md)" }}>
              {/* Assessment Type */}
              <div>
                <label htmlFor="assessment-type">Assessment Type</label>
                <select id="assessment-type" value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
                  <option value="vendor">Vendor Due Diligence</option>
                  <option value="ma">M&A Assessment</option>
                </select>
              </div>

              {/* Subject Name */}
              <div>
                <label htmlFor="subject-name">Subject Name</label>
                <input
                  id="subject-name"
                  type="text"
                  value={subjectName}
                  onChange={(e) => setSubjectName(e.target.value)}
                  placeholder="e.g. Acme Cloud Analytics"
                />
              </div>

              {/* Document Source */}
              <div>
                <label style={{ marginBottom: "var(--space-sm)" }}>Document Source</label>
                <SourceToggle value={sourceType} onChange={setSourceType} />
              </div>

              {/* Conditional: Demo Scenario or Drive URL */}
              {sourceType === "demo" ? (
                <div>
                  <label htmlFor="demo-scenario">Demo Scenario</label>
                  <select
                    id="demo-scenario"
                    value={packetPath}
                    onChange={(e) => {
                      const val = e.target.value;
                      setPacketPath(val);
                      if (val === "examples/tprm/acme") {
                        setSubjectName("Acme Cloud Analytics");
                        setMode("vendor");
                      } else {
                        setSubjectName("HashiCorp Inc.");
                        setMode("ma");
                      }
                    }}
                  >
                    <option value="examples/tprm/acme">Acme Cloud Analytics — Vendor Due Diligence</option>
                    <option value="examples/tprm/hashicorp">HashiCorp Inc. — M&amp;A Assessment</option>
                  </select>
                </div>
              ) : (
                <div>
                  <label htmlFor="drive-url">Google Drive Folder URL</label>
                  <input
                    id="drive-url"
                    type="url"
                    value={driveFolderUrl}
                    onChange={(e) => setDriveFolderUrl(e.target.value)}
                    placeholder="https://drive.google.com/drive/folders/…"
                  />
                  <div
                    style={{
                      fontSize: 12,
                      color: "var(--md-sys-color-on-surface-variant)",
                      marginTop: "var(--space-xs)",
                      opacity: 0.45,
                    }}
                  >
                    Share the folder with your service account before running.
                  </div>
                </div>
              )}

              {/* Run Assessment button */}
              <button
                onClick={startRun}
                disabled={isRunDisabled}
                onMouseEnter={() => setRunBtnHovered(true)}
                onMouseLeave={() => { setRunBtnHovered(false); setRunBtnActive(false); }}
                onMouseDown={() => setRunBtnActive(true)}
                onMouseUp={() => setRunBtnActive(false)}
                style={{
                  background: runBtnBg,
                  color: "var(--md-sys-color-on-primary)",
                  padding: "12px var(--space-lg)",
                  fontSize: 14,
                  fontWeight: 500,
                  borderRadius: "var(--md-sys-shape-small)",
                  border: "none",
                  width: "100%",
                  height: 48,
                  marginTop: "var(--space-sm)",
                  boxShadow: isRunDisabled ? "none" : runBtnShadow,
                  opacity: submitting ? 0.80 : isRunDisabled ? 0.38 : 1,
                  transition: "background 150ms ease, box-shadow 150ms ease, opacity 150ms ease, transform 80ms ease",
                  transform: `scale(${runBtnScale})`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "var(--space-xs)",
                  cursor: isRunDisabled ? "not-allowed" : "pointer",
                }}
              >
                {submitting ? (
                  <>
                    <span
                      style={{
                        width: 16,
                        height: 16,
                        border: "2px solid rgba(255,255,255,0.30)",
                        borderTopColor: "#ffffff",
                        borderRadius: "50%",
                        display: "inline-block",
                        animation: "spin 700ms linear infinite",
                        flexShrink: 0,
                      }}
                    />
                    Starting...
                  </>
                ) : (
                  <>
                    <span
                      className="material-symbols-outlined"
                      style={{
                        fontSize: 18,
                        fontVariationSettings: "'FILL' 0, 'wght' 400",
                      }}
                    >
                      arrow_forward
                    </span>
                    Run Assessment
                  </>
                )}
              </button>
            </div>
          </div>
        ) : (
          /* ── Run Dashboard ── */
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "260px 1fr",
              gap: "var(--space-lg)",
              alignItems: "start",
            }}
          >
            {/* Left: Pipeline panel */}
            <div
              style={{
                background: "var(--md-sys-color-surface)",
                border: "1px solid var(--md-sys-color-outline)",
                borderRadius: "var(--md-sys-shape-large)",
                boxShadow: "var(--md-sys-elevation-1)",
                padding: "var(--space-lg)",
                position: "sticky",
                top: "var(--space-lg)",
              }}
            >
              {/* Subject header block */}
              <div style={{ marginBottom: "var(--space-md)" }}>
                <div
                  style={{
                    fontSize: 12,
                    fontWeight: 500,
                    color: "var(--md-sys-color-on-surface-variant)",
                    textTransform: "uppercase",
                    letterSpacing: "0.08em",
                    marginBottom: "var(--space-xs)",
                  }}
                >
                  {rs.mode === "ma" ? "M&A Assessment" : "Vendor Assessment"}
                </div>
                <div
                  style={{
                    fontWeight: 500,
                    fontSize: 16,
                    color: "var(--md-sys-color-on-surface)",
                    lineHeight: 1.35,
                  }}
                >
                  {rs.subject}
                </div>
              </div>

              {/* Pipeline step list */}
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "var(--space-xs)",
                  marginBottom: "var(--space-sm)",
                  position: "relative",
                }}
              >
                {rs.pipeline.map((node) => {
                  const done = rs.completedNodes.includes(node);
                  const activeIdx = rs.completedNodes.length;
                  const nodeIdx = rs.pipeline.indexOf(node);
                  const active = rs.phase === "running" && nodeIdx === activeIdx;
                  return (
                    <PipelineStep
                      key={node}
                      node={node}
                      label={rs.nodeLabels[node] ?? node}
                      done={done}
                      active={active}
                    />
                  );
                })}
              </div>

              {/* Panel footer */}
              <div
                style={{
                  borderTop: "1px solid var(--md-sys-color-outline)",
                  paddingTop: "var(--space-sm)",
                  marginTop: "var(--space-sm)",
                }}
              >
                {rs.phase === "running" && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--space-xs)",
                      fontSize: 12,
                      color: "var(--md-sys-color-on-surface-variant)",
                    }}
                  >
                    <span
                      className="material-symbols-outlined pipeline-spin"
                      style={{
                        fontSize: 16,
                        color: "var(--md-sys-color-primary)",
                        fontVariationSettings: "'FILL' 0, 'wght' 400",
                      }}
                    >
                      sync
                    </span>
                    Running · {fmtDuration(rs.elapsedSec)}
                  </div>
                )}
                {rs.phase === "done" && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--space-xs)",
                      fontSize: 12,
                      color: "var(--color-verdict-approve)",
                    }}
                  >
                    <span
                      className="material-symbols-outlined"
                      style={{
                        fontSize: 16,
                        color: "var(--color-verdict-approve)",
                        fontVariationSettings: "'FILL' 1, 'wght' 400",
                      }}
                    >
                      check_circle
                    </span>
                    Complete · {fmtDuration(rs.elapsedSec)}
                  </div>
                )}
                {rs.phase === "error" && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--space-xs)",
                      fontSize: 12,
                      color: "var(--md-sys-color-error)",
                    }}
                  >
                    <span
                      className="material-symbols-outlined"
                      style={{
                        fontSize: 16,
                        color: "var(--md-sys-color-error)",
                        fontVariationSettings: "'FILL' 1, 'wght' 400",
                      }}
                    >
                      error
                    </span>
                    Analysis Failed
                  </div>
                )}
                {/* Run ID — decorative, Label role at reduced opacity */}
                <div
                  style={{
                    marginTop: "var(--space-xs)",
                    fontSize: 12,
                    fontWeight: 400,
                    color: "var(--md-sys-color-outline)",
                    opacity: 0.45,
                  }}
                  title={`Assessment ID: ${rs.runId}`}
                >
                  {rs.runId.slice(0, 12)}…
                </div>
              </div>
            </div>

            {/* Right: main content */}
            <div>
              {/* Waiting state — running, no verdict yet */}
              {rs.phase === "running" && !rs.verdict && (
                <div
                  role="status"
                  aria-live="polite"
                  aria-label="Analysis in progress"
                  style={{
                    background: "var(--md-sys-color-surface)",
                    border: "1px solid var(--md-sys-color-outline)",
                    borderRadius: "var(--md-sys-shape-large)",
                    boxShadow: "var(--md-sys-elevation-1)",
                    padding: "var(--space-2xl) var(--space-xl)",
                    textAlign: "center",
                  }}
                >
                  {/* Spinner */}
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      border: "3px solid var(--md-sys-color-surface-container-highest)",
                      borderTopColor: "var(--md-sys-color-primary)",
                      borderRadius: "50%",
                      animation: "spin 800ms linear infinite",
                      margin: "0 auto var(--space-md)",
                    }}
                  />
                  <div
                    style={{
                      fontWeight: 500,
                      fontSize: 16,
                      color: "var(--md-sys-color-on-surface)",
                    }}
                  >
                    Analysis in Progress
                  </div>
                  <div
                    style={{
                      fontSize: 14,
                      fontWeight: 400,
                      color: "var(--md-sys-color-on-surface-variant)",
                      marginTop: "var(--space-sm)",
                    }}
                  >
                    {rs.completedNodes.length} of {rs.pipeline.length} stages complete
                  </div>

                  {/* Progress bar */}
                  <div
                    style={{
                      width: 200,
                      height: 4,
                      background: "var(--md-sys-color-surface-container-highest)",
                      borderRadius: 2,
                      margin: "var(--space-sm2) auto 0",
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        height: "100%",
                        background: "var(--md-sys-color-primary)",
                        borderRadius: 2,
                        width: `${rs.pipeline.length > 0
                          ? (rs.completedNodes.length / rs.pipeline.length) * 100
                          : 0}%`,
                        transition: "width 400ms cubic-bezier(0.4,0,0.2,1)",
                      }}
                    />
                  </div>
                </div>
              )}

              {/* Verdict card */}
              {rs.verdict && <VerdictCard data={rs.verdict} />}

              {/* Error banner */}
              {rs.phase === "error" && (
                <div
                  style={{
                    background: "rgba(242,69,61,0.10)",
                    border: "1px solid rgba(242,69,61,0.30)",
                    borderRadius: "var(--md-sys-shape-large)",
                    padding: "var(--space-lg)",
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "var(--space-sm)",
                  }}
                >
                  <span
                    className="material-symbols-outlined"
                    style={{
                      fontSize: 20,
                      color: "var(--md-sys-color-error)",
                      fontVariationSettings: "'FILL' 1, 'wght' 400",
                      flexShrink: 0,
                      lineHeight: 1.35,
                    }}
                  >
                    error
                  </span>
                  <div>
                    <div
                      style={{
                        fontWeight: 500,
                        fontSize: 16,
                        color: "var(--md-sys-color-error)",
                        marginBottom: "var(--space-xs)",
                      }}
                    >
                      Assessment Failed
                    </div>
                    {/* Para 1: raw technical detail */}
                    <p
                      style={{
                        fontSize: 14,
                        fontWeight: 400,
                        fontFamily: "'Roboto Mono', monospace",
                        color: "var(--md-sys-color-on-error-container)",
                        margin: 0,
                      }}
                    >
                      {rs.error}
                    </p>
                    {/* Para 2: solution path — always shown */}
                    <p
                      style={{
                        fontSize: 14,
                        fontWeight: 400,
                        color: "var(--md-sys-color-on-surface-variant)",
                        marginTop: "var(--space-sm)",
                        marginBottom: 0,
                      }}
                    >
                      Check that your Google Drive folder is shared with the service account,
                      then select &lsquo;New Assessment&rsquo; to try again. If the problem persists,
                      contact your administrator.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
