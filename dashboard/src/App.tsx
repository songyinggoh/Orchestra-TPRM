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

const SEV_COLOR: Record<string, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#f59e0b",
  low: "#22c55e",
};

const VERDICT_COLOR: Record<string, string> = {
  reject: "#ef4444",
  conditional: "#f59e0b",
  approve: "#22c55e",
};

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

// ── Sub-components ────────────────────────────────────────────────────────────

function PipelineStep({
  node, label, done, active,
}: { node: string; label: string; done: boolean; active: boolean }) {
  const isSpecialist = ["LegalAgent", "SecurityAgent", "ExternalAgent", "CodeAgent", "FinancialAgent"].includes(node);
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10,
      padding: "8px 12px",
      background: done ? "rgba(91,110,245,0.12)" : active ? "rgba(91,110,245,0.06)" : "transparent",
      borderRadius: 6,
      borderLeft: `3px solid ${done ? "var(--accent)" : active ? "var(--accent-light)" : "var(--border)"}`,
      transition: "all 0.3s",
      marginLeft: isSpecialist ? 24 : 0,
    }}>
      <span style={{
        fontSize: 16,
        filter: done ? "none" : "grayscale(1) opacity(0.4)",
      }}>
        {done ? "✓" : active ? "⟳" : "○"}
      </span>
      <span style={{
        fontSize: 13,
        color: done ? "var(--text)" : "var(--muted)",
        fontWeight: done ? 500 : 400,
      }}>
        {label}
      </span>
    </div>
  );
}

function VerdictCard({ data }: { data: VerdictData }) {
  const verdict = data.policy_verdict.toLowerCase();
  const color = VERDICT_COLOR[verdict] ?? "#8b8fa8";
  const sevCounts = groupBySeverity(data.findings);

  return (
    <div style={{
      background: "var(--surface)",
      border: `1px solid ${color}40`,
      borderRadius: "var(--radius)",
      padding: 24,
    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 20 }}>
        <div style={{
          background: `${color}22`,
          border: `1px solid ${color}`,
          borderRadius: 8,
          padding: "6px 16px",
          fontSize: 18,
          fontWeight: 700,
          color,
          textTransform: "uppercase",
          letterSpacing: "0.1em",
        }}>
          {data.policy_verdict}
        </div>
        <div>
          <div style={{ fontSize: 28, fontWeight: 700, color: "var(--text)" }}>
            {data.risk_score.toLocaleString()}
          </div>
          <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase" }}>Risk Score</div>
        </div>
        <div style={{ marginLeft: "auto", textAlign: "right" }}>
          <div style={{ fontSize: 24, fontWeight: 600 }}>{data.findings_count}</div>
          <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase" }}>Findings</div>
        </div>
      </div>

      {/* Severity breakdown */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
        {(["critical", "high", "medium", "low"] as const).map((sev) => (
          <div key={sev} style={{
            background: `${SEV_COLOR[sev]}18`,
            border: `1px solid ${SEV_COLOR[sev]}50`,
            borderRadius: 6,
            padding: "4px 12px",
            fontSize: 13,
            color: SEV_COLOR[sev],
            fontWeight: 600,
          }}>
            {sevCounts[sev]} {sev}
          </div>
        ))}
      </div>

      {/* Findings table */}
      {data.findings.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table style={{
            width: "100%", borderCollapse: "collapse", fontSize: 13,
          }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                {["Agent", "Category", "Severity", "Summary"].map((h) => (
                  <th key={h} style={{
                    textAlign: "left", padding: "8px 10px",
                    color: "var(--muted)", fontWeight: 600,
                    fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em",
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.findings.slice(0, 50).map((f, i) => (
                <tr key={i} style={{
                  borderBottom: "1px solid var(--border)",
                  background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)",
                }}>
                  <td style={{ padding: "8px 10px", color: "var(--muted)", whiteSpace: "nowrap" }}>{f.agent}</td>
                  <td style={{ padding: "8px 10px", whiteSpace: "nowrap" }}>{f.category}</td>
                  <td style={{ padding: "8px 10px" }}>
                    <span style={{
                      color: SEV_COLOR[f.severity] ?? "var(--muted)",
                      fontWeight: 600,
                    }}>
                      {f.severity}
                    </span>
                  </td>
                  <td style={{ padding: "8px 10px", color: "var(--muted)", maxWidth: 400 }}>{f.summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.findings.length > 50 && (
            <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 8 }}>
              + {data.findings.length - 50} more findings
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
      alert(String(err));
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

  return (
    <div style={{
      minHeight: "100vh",
      background: "var(--bg)",
      display: "flex",
      flexDirection: "column",
    }}>
      {/* Header */}
      <header style={{
        borderBottom: "1px solid var(--border)",
        padding: "16px 32px",
        display: "flex",
        alignItems: "center",
        gap: 16,
        background: "var(--surface)",
      }}>
        <div style={{
          width: 32, height: 32, borderRadius: 8,
          background: "var(--accent)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 18,
        }}>🎻</div>
        <div>
          <div style={{ fontWeight: 700, fontSize: 16 }}>Orchestra TPRM</div>
          <div style={{ fontSize: 11, color: "var(--muted)" }}>Multi-Agent Risk Platform · Gemini 2.5 Flash</div>
        </div>
        {rs && (
          <button
            onClick={reset}
            style={{ marginLeft: "auto", background: "var(--surface2)", color: "var(--muted)", padding: "6px 14px" }}
          >
            ← New Run
          </button>
        )}
      </header>

      <main style={{ flex: 1, padding: "32px", maxWidth: 1100, margin: "0 auto", width: "100%" }}>
        {!rs ? (
          /* ── Run Form ── */
          <div style={{ maxWidth: 520, margin: "60px auto" }}>
            <h2 style={{ marginBottom: 8, fontSize: 22 }}>New Assessment</h2>
            <p style={{ color: "var(--muted)", marginBottom: 32, fontSize: 14 }}>
              Submit a vendor or M&A packet for multi-agent TPRM analysis.
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              <div>
                <label>Assessment Type</label>
                <select value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
                  <option value="vendor">Vendor Due Diligence</option>
                  <option value="ma">M&A Assessment</option>
                </select>
              </div>

              <div>
                <label>Subject Name</label>
                <input
                  type="text"
                  value={subjectName}
                  onChange={(e) => setSubjectName(e.target.value)}
                  placeholder="e.g. Acme Cloud Analytics"
                />
              </div>

              {/* Source selector */}
              <div>
                <label style={{ marginBottom: 8, display: "block" }}>Document Source</label>
                <div style={{ display: "flex", gap: 0, border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
                  {(["demo", "drive"] as const).map((opt) => (
                    <button
                      key={opt}
                      onClick={() => setSourceType(opt)}
                      style={{
                        flex: 1,
                        padding: "9px 0",
                        fontSize: 13,
                        background: sourceType === opt ? "var(--accent)" : "var(--surface2)",
                        color: sourceType === opt ? "#fff" : "var(--muted)",
                        border: "none",
                        borderRadius: 0,
                        cursor: "pointer",
                      }}
                    >
                      {opt === "demo" ? "Demo packet" : "Google Drive folder"}
                    </button>
                  ))}
                </div>
              </div>

              {sourceType === "demo" ? (
                <div>
                  <label>Demo Preset</label>
                  <select
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
                  <label>Google Drive Folder URL</label>
                  <input
                    type="url"
                    value={driveFolderUrl}
                    onChange={(e) => setDriveFolderUrl(e.target.value)}
                    placeholder="https://drive.google.com/drive/folders/…"
                  />
                  <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
                    Share the folder with your service account before running
                  </div>
                </div>
              )}

              <button
                onClick={startRun}
                disabled={
                  submitting || !subjectName ||
                  (sourceType === "demo" ? !packetPath : !driveFolderUrl)
                }
                style={{
                  background: "var(--accent)",
                  color: "#fff",
                  padding: "12px 24px",
                  fontSize: 15,
                  borderRadius: 8,
                  marginTop: 8,
                }}
              >
                {submitting ? "Starting…" : "Run Assessment →"}
              </button>
            </div>
          </div>
        ) : (
          /* ── Run Dashboard ── */
          <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 24, alignItems: "start" }}>
            {/* Left: Pipeline progress */}
            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: 20 }}>
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", marginBottom: 4 }}>
                  {rs.mode === "ma" ? "M&A Assessment" : "Vendor Assessment"}
                </div>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{rs.subject}</div>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 16 }}>
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

              {/* Status / elapsed */}
              <div style={{
                borderTop: "1px solid var(--border)",
                paddingTop: 12,
                fontSize: 12,
                color: "var(--muted)",
              }}>
                {rs.phase === "running" && (
                  <div>⟳ Running · {fmtDuration(rs.elapsedSec)}</div>
                )}
                {rs.phase === "done" && (
                  <div style={{ color: "var(--green)" }}>✓ Complete · {fmtDuration(rs.elapsedSec)}</div>
                )}
                {rs.phase === "error" && (
                  <div style={{ color: "var(--red)" }}>✗ Error</div>
                )}
                <div style={{ marginTop: 4, fontSize: 11, color: "var(--border)" }}>
                  run: {rs.runId.slice(0, 12)}…
                </div>
              </div>
            </div>

            {/* Right: Main content */}
            <div>
              {rs.phase === "running" && !rs.verdict && (
                <div style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius)",
                  padding: 40,
                  textAlign: "center",
                  color: "var(--muted)",
                }}>
                  <div style={{ fontSize: 32, marginBottom: 16 }}>⟳</div>
                  <div style={{ fontWeight: 500 }}>Specialists running…</div>
                  <div style={{ fontSize: 13, marginTop: 8 }}>
                    {rs.completedNodes.length} / {rs.pipeline.length} nodes complete
                  </div>
                </div>
              )}

              {rs.verdict && <VerdictCard data={rs.verdict} />}

              {rs.phase === "error" && (
                <div style={{
                  background: "rgba(239,68,68,0.1)",
                  border: "1px solid rgba(239,68,68,0.3)",
                  borderRadius: "var(--radius)",
                  padding: 24,
                  color: "var(--red)",
                }}>
                  <div style={{ fontWeight: 600, marginBottom: 8 }}>Run failed</div>
                  <div style={{ fontSize: 13, fontFamily: "monospace" }}>{rs.error}</div>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
