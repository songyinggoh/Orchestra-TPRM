# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace MD3 dark theme with a pure-black B2 layout — 48px command bar, 56px horizontal pipeline timeline, split live-log / verdict canvas, centred scoping form when idle.

**Architecture:** Three vertically-stacked zones. `index.css` gets a 12-token design system replacing all `--md-sys-color-*` vars. `App.tsx` adds `CommandBar` and `PipelineTimeline` components, removes `PipelineStep` / `SourceToggle` / `ScopingScreen`, rewrites the `App` function to the B2 layout with a log-state SSE column. `index.html` gains Google Sans + Roboto Mono imports (missing from current file).

**Tech Stack:** React 19, TypeScript 5, Vite — no new npm dependencies.

---

### Task 1: Add Google Sans + Roboto Mono to `index.html`

**Files:**
- Modify: `dashboard/index.html`

- [ ] **Step 1: Add font links**

Replace the existing Roboto `<link>` (line 10 of `dashboard/index.html`):
```html
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
```
with:
```html
    <link href="https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;600&family=Roboto+Mono:wght@400;500;700&family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
```

- [ ] **Step 2: Commit**
```bash
git add Orchestra/dashboard/index.html
git commit -m "style: add Google Sans + Roboto Mono font imports"
```

---

### Task 2: Replace CSS design tokens in `index.css`

**Files:**
- Modify: `dashboard/src/index.css`

- [ ] **Step 1: Replace the entire `:root {}` block**

Replace lines 1–76 of `dashboard/src/index.css` (from `:root {` through its closing `}`) with:

```css
:root {
  --bg:             #000000;
  --surface-1:      #0c0c0c;
  --surface-2:      #111111;
  --surface-3:      #141414;
  --border:         rgba(255,255,255,0.08);
  --border-strong:  rgba(255,255,255,0.14);
  --text-primary:   #ffffff;
  --text-secondary: rgba(255,255,255,0.45);
  --text-muted:     rgba(255,255,255,0.25);
  --accent:         #94a3c0;

  --sev-critical: #ea4335;
  --sev-high:     #fa7b17;
  --sev-medium:   #fbbc04;
  --sev-low:      #34a853;

  --radius-sm: 8px;
  --radius-md: 10px;
}
```

- [ ] **Step 2: Replace `body` block**

Replace the `body { ... }` block (lines 80–88) with:
```css
body {
  background: var(--bg);
  color: var(--text-primary);
  min-height: 100vh;
  font-family: 'Google Sans', 'Roboto', sans-serif;
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
```

- [ ] **Step 3: Replace `input, select, textarea` block**

Replace the `input, select, textarea { ... }` block and all associated hover/focus/disabled rules (lines 92–127) with:
```css
input, select, textarea {
  background: var(--surface-3);
  border: 1px solid var(--border);
  color: var(--text-primary);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 14px;
  font-family: 'Google Sans', 'Roboto', sans-serif;
  width: 100%;
  outline: none;
  transition: border-color 150ms ease;
}

input:hover, select:hover, textarea:hover {
  border-color: var(--border-strong);
}

input:focus, select:focus, textarea:focus {
  border-color: var(--border-strong);
}

input:disabled, select:disabled {
  opacity: 0.38;
  cursor: not-allowed;
}

select {
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='20' viewBox='0 0 24 24' fill='%23ffffff'%3E%3Cpath d='M7 10l5 5 5-5z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  height: 38px;
}

textarea {
  resize: vertical;
  min-height: 80px;
}
```

- [ ] **Step 4: Replace `button` block**

Replace the `button { ... }` block and its disabled/focus rules (lines 128–153) with:
```css
button {
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  font-family: 'Google Sans', 'Roboto', sans-serif;
  border: none;
  border-radius: var(--radius-sm);
  padding: 10px 20px;
  transition: background 150ms ease, opacity 150ms ease;
}

button:disabled {
  opacity: 0.38;
  cursor: not-allowed;
}

button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

input:focus-visible,
select:focus-visible,
textarea:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 0;
}
```

- [ ] **Step 5: Replace `label` block**

Replace the `label { ... }` block (lines 155–164) with:
```css
label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  font-family: 'Google Sans', 'Roboto', sans-serif;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 4px;
}
```

- [ ] **Step 6: Add `pulse` and `blink-cursor` keyframes**

After the existing `@keyframes verdict-reveal` block, add:
```css
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.4; transform: scale(0.75); }
}

@keyframes blink-cursor {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
}
```

- [ ] **Step 7: Verify no `--md-sys-` remain in index.css**
```powershell
Select-String -Path "Orchestra\dashboard\src\index.css" -Pattern "md-sys"
```
Expected: no output.

- [ ] **Step 8: Commit**
```bash
git add Orchestra/dashboard/src/index.css
git commit -m "style: replace MD3 tokens with B2 design system in index.css"
```

---

### Task 3: Bulk-replace CSS var names in `App.tsx`

**Files:**
- Modify: `dashboard/src/App.tsx`

This task replaces every `var(--md-sys-*)` and `var(--space-*)` reference. No logic changes.

- [ ] **Step 1: Run substitution script from the repo root**

```powershell
$file = "Orchestra\dashboard\src\App.tsx"
$content = Get-Content $file -Raw
$replacements = @(
  @("var(--md-sys-color-background)",              "var(--bg)"),
  @("var(--md-sys-color-surface-container-highest)","var(--surface-3)"),
  @("var(--md-sys-color-surface-container-high)",  "var(--surface-3)"),
  @("var(--md-sys-color-surface-container)",       "var(--surface-3)"),
  @("var(--md-sys-color-surface-variant)",         "var(--surface-3)"),
  @("var(--md-sys-color-surface)",                 "var(--surface-2)"),
  @("var(--md-sys-color-outline-variant)",         "var(--border)"),
  @("var(--md-sys-color-outline)",                 "var(--border)"),
  @("var(--md-sys-color-on-surface-variant)",      "var(--text-secondary)"),
  @("var(--md-sys-color-on-surface)",              "var(--text-primary)"),
  @("var(--md-sys-color-primary-container)",       "var(--surface-3)"),
  @("var(--md-sys-color-on-primary-container)",    "var(--accent)"),
  @("var(--md-sys-color-on-primary)",              "var(--text-primary)"),
  @("var(--md-sys-color-primary)",                 "var(--accent)"),
  @("var(--md-sys-color-error)",                   "var(--sev-critical)"),
  @("var(--md-sys-color-on-error-container)",      "var(--text-primary)"),
  @("var(--color-verdict-approve)",                "var(--sev-low)"),
  @("var(--md-sys-shape-large)",                   "var(--radius-md)"),
  @("var(--md-sys-shape-medium)",                  "var(--radius-md)"),
  @("var(--md-sys-shape-small)",                   "var(--radius-sm)"),
  @("var(--md-sys-shape-extra-small)",             "6px"),
  @("var(--md-sys-elevation-1)",                   "none"),
  @("var(--md-sys-elevation-2)",                   "none"),
  @("var(--md-sys-elevation-3)",                   "none"),
  @("var(--space-xs)",                             "4px"),
  @("var(--space-sm2)",                            "12px"),
  @("var(--space-sm)",                             "8px"),
  @("var(--space-md)",                             "16px"),
  @("var(--space-lg)",                             "24px"),
  @("var(--space-xl)",                             "32px"),
  @("var(--space-2xl)",                            "48px")
)
foreach ($pair in $replacements) {
  $content = $content.Replace($pair[0], $pair[1])
}
Set-Content $file $content -Encoding utf8
```

- [ ] **Step 2: Verify no `--md-sys-` remain**
```powershell
Select-String -Path "Orchestra\dashboard\src\App.tsx" -Pattern "md-sys"
```
Expected: no output.

- [ ] **Step 3: Commit**
```bash
git add Orchestra/dashboard/src/App.tsx
git commit -m "style: bulk-replace MD3 vars with B2 tokens in App.tsx"
```

---

### Task 4: Remove dead components from `App.tsx`

**Files:**
- Modify: `dashboard/src/App.tsx`

Remove four code blocks that are no longer used after the layout redesign.

- [ ] **Step 1: Remove `SPECIALIST_NODES` constant**

Remove these 3 lines (around line 158 after Task 3):
```tsx
// Specialist nodes that get left-indented
const SPECIALIST_NODES = new Set([
  "LegalAgent", "SecurityAgent", "ExternalAgent", "CodeAgent", "FinancialAgent",
]);
```

- [ ] **Step 2: Remove `PipelineStep` component**

Remove the entire block from `// ── PipelineStep` through the component's closing `}` (≈ lines 175–273 before removal of SPECIALIST_NODES).

- [ ] **Step 3: Remove `SourceToggle` component**

Remove the entire block from `// ── SourceToggle` through its closing `}` (≈ lines 275–358).

- [ ] **Step 4: Remove `ScopingScreen` component**

Remove the entire block from `// ── ScopingScreen` through its closing `}` (≈ lines 784–1061 with line numbers shifting after previous removals).

- [ ] **Step 5: Remove `DEFAULT_WORKSTREAMS` constant**

Remove this line (used only by ScopingScreen):
```tsx
const DEFAULT_WORKSTREAMS: MAScope["active_workstreams"] = [
  "legal", "financial", "tech", "commercial", "hr", "esg", "regulatory",
];
```

- [ ] **Step 6: Commit (TypeScript errors are expected — resolved in Task 6)**
```bash
git add Orchestra/dashboard/src/App.tsx
git commit -m "refactor: remove PipelineStep, SourceToggle, ScopingScreen, SPECIALIST_NODES"
```

---

### Task 5: Add `DISPLAY_STEPS` constants + `PipelineTimeline` component

**Files:**
- Modify: `dashboard/src/App.tsx` (insert after `WS_COLOR` constant, before helpers)

- [ ] **Step 1: Add `DisplayStep` interface and constants**

After the `WS_COLOR` block, insert:

```tsx
// ── Pipeline display steps ────────────────────────────────────────────────────

interface DisplayStep {
  id: string;
  label: string;
  nodes: Set<string>;
}

const VENDOR_DISPLAY_STEPS: DisplayStep[] = [
  { id: "intake",      label: "Intake",      nodes: new Set(["bootstrap_node", "intake_node", "router"]) },
  { id: "specialists", label: "Specialists", nodes: new Set(["LegalAgent", "SecurityAgent", "ExternalAgent", "CodeAgent"]) },
  { id: "policy",      label: "Policy",      nodes: new Set(["policy"]) },
  { id: "coordinator", label: "Coordinator", nodes: new Set(["coordinator"]) },
];

const MA_DISPLAY_STEPS: DisplayStep[] = [
  { id: "intake",      label: "Intake",      nodes: new Set(["bootstrap_node", "intake_node", "router"]) },
  { id: "vdr",         label: "VDR Gate",    nodes: new Set(["vdr_gate"]) },
  { id: "specialists", label: "Specialists", nodes: new Set(["LegalAgent", "SecurityAgent", "ExternalAgent", "CodeAgent", "FinancialAgent", "SaaSMetricsAgent"]) },
  { id: "policy",      label: "Policy",      nodes: new Set(["policy"]) },
  { id: "coordinator", label: "Coordinator", nodes: new Set(["coordinator"]) },
  { id: "pmi",         label: "PMI Plan",    nodes: new Set(["pmi_planner"]) },
];
```

- [ ] **Step 2: Add `PipelineTimeline` component**

After the `groupBySeverity` helper, insert:

```tsx
// ── PipelineTimeline ──────────────────────────────────────────────────────────

function PipelineTimeline({
  mode, completedNodes, phase,
}: { mode: Mode; completedNodes: string[]; phase: Phase }) {
  const steps = mode === "ma" ? MA_DISPLAY_STEPS : VENDOR_DISPLAY_STEPS;
  const doneSet = new Set(completedNodes);

  return (
    <div
      style={{
        height: 56,
        background: "var(--surface-1)",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        alignItems: "flex-start",
        padding: "10px 20px 0",
        flexShrink: 0,
      }}
    >
      {steps.map((step, idx) => {
        const done = [...step.nodes].some((n) => doneSet.has(n));
        const prevDone = idx === 0 || [...steps[idx - 1].nodes].some((n) => doneSet.has(n));
        const active = phase === "running" && !done && prevDone;

        return (
          <React.Fragment key={step.id}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3, flexShrink: 0 }}>
              <div
                style={{
                  width: 20, height: 20,
                  borderRadius: "50%",
                  border: done ? "none" : active
                    ? "1.5px solid rgba(255,255,255,0.85)"
                    : "1.5px solid rgba(255,255,255,0.2)",
                  background: done ? "#ffffff" : active ? "rgba(255,255,255,0.06)" : "transparent",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  flexShrink: 0,
                  transition: "background 250ms ease, border-color 250ms ease",
                }}
              >
                {done && (
                  <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
                    <path d="M1.5 5.5l3 3 5-5" stroke="#000" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
                {active && (
                  <div
                    style={{
                      width: 6, height: 6, borderRadius: "50%",
                      background: "#ffffff",
                      animation: "pulse 1.4s ease-in-out infinite",
                    }}
                  />
                )}
              </div>
              <span
                style={{
                  fontSize: 10,
                  fontFamily: "'Google Sans', sans-serif",
                  color: done || active ? "var(--text-primary)" : "var(--text-muted)",
                  fontWeight: done || active ? 500 : 400,
                  whiteSpace: "nowrap",
                  lineHeight: 1,
                }}
              >
                {step.label}
              </span>
            </div>

            {idx < steps.length - 1 && (
              <div
                style={{
                  flex: 1,
                  height: 1,
                  background: done ? "rgba(255,255,255,0.3)" : "rgba(255,255,255,0.07)",
                  marginTop: 9,
                  transition: "background 300ms ease",
                }}
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Commit**
```bash
git add Orchestra/dashboard/src/App.tsx
git commit -m "feat: add PipelineTimeline horizontal component"
```

---

### Task 6: Add `CommandBar` + rewrite `App` function

**Files:**
- Modify: `dashboard/src/App.tsx`

- [ ] **Step 1: Add `CommandBar` component before `// ── Main App`**

Insert:

```tsx
// ── CommandBar ────────────────────────────────────────────────────────────────

function CommandBar({
  runState,
  onNewRun,
}: { runState: RunState | null; onNewRun: () => void }) {
  return (
    <div
      style={{
        height: 48,
        background: "var(--surface-1)",
        borderBottom: "1px solid var(--border)",
        padding: "0 16px",
        display: "flex",
        alignItems: "center",
        gap: 10,
        flexShrink: 0,
      }}
    >
      {/* Logo + wordmark */}
      <div style={{ display: "flex", alignItems: "center", gap: 7, flexShrink: 0 }}>
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <circle cx="10" cy="4"  r="2.2" fill="var(--accent)" />
          <circle cx="4"  cy="14" r="2.2" fill="var(--accent)" />
          <circle cx="16" cy="14" r="2.2" fill="var(--accent)" />
          <line x1="10" y1="6"   x2="4.8"  y2="12.2" stroke="var(--accent)" strokeWidth="1.2" />
          <line x1="10" y1="6"   x2="15.2" y2="12.2" stroke="var(--accent)" strokeWidth="1.2" />
          <line x1="6.2" y1="14" x2="13.8" y2="14"   stroke="var(--accent)" strokeWidth="1.2" />
        </svg>
        <span
          style={{
            fontFamily: "'Google Sans', 'Roboto', sans-serif",
            fontWeight: 600,
            fontSize: 14,
            color: "var(--text-primary)",
            letterSpacing: "0.01em",
          }}
        >
          Orchestra TPRM
        </span>
      </div>

      {/* Active run pill (centre) */}
      <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
        {runState && (
          <div
            style={{
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "4px 14px",
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              fontSize: 13,
            }}
          >
            <span style={{ fontFamily: "'Google Sans', 'Roboto', sans-serif", fontWeight: 500, color: "var(--text-primary)" }}>
              {runState.subject}
            </span>
            <span style={{ color: "var(--text-secondary)" }}>·</span>
            <span style={{ fontFamily: "'Google Sans', 'Roboto', sans-serif", color: "var(--text-secondary)" }}>
              {runState.mode === "ma" ? "M&A Due Diligence" : "Vendor Assessment"}
            </span>
            {runState.phase === "running" && (
              <>
                <span style={{ color: "var(--text-secondary)" }}>·</span>
                <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <span
                    style={{
                      width: 6, height: 6, borderRadius: "50%",
                      background: "var(--accent)",
                      display: "inline-block",
                      animation: "pulse 1.4s ease-in-out infinite",
                    }}
                  />
                  <span
                    style={{
                      fontFamily: "'Roboto Mono', monospace",
                      fontSize: 11,
                      color: "var(--accent)",
                    }}
                  >
                    running
                  </span>
                </span>
              </>
            )}
            {runState.phase === "done" && (
              <>
                <span style={{ color: "var(--text-secondary)" }}>·</span>
                <span
                  style={{
                    fontFamily: "'Roboto Mono', monospace",
                    fontSize: 11,
                    color: "var(--sev-low)",
                  }}
                >
                  complete · {fmtDuration(runState.elapsedSec)}
                </span>
              </>
            )}
          </div>
        )}
      </div>

      {/* Right actions */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
        <button
          onClick={onNewRun}
          style={{
            background: "#ffffff",
            color: "#000000",
            border: "none",
            borderRadius: 8,
            padding: "5px 14px",
            fontSize: 13,
            fontFamily: "'Google Sans', 'Roboto', sans-serif",
            fontWeight: 500,
            cursor: "pointer",
          }}
        >
          + New Run
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Replace the entire `App` function**

Replace everything from `export default function App()` through the end of the file with:

```tsx
// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const [mode, setMode] = useState<Mode>("vendor");
  const [subjectName, setSubjectName] = useState("Acme Cloud Analytics");
  const [docUrls, setDocUrls] = useState("");
  const [runState, setRunState] = useState<RunState | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [logLines, setLogLines] = useState<{ text: string; level: "info" | "warn" | "error" }[]>([]);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const esRef   = useRef<EventSource | null>(null);
  const logEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    return () => {
      timerRef.current && clearInterval(timerRef.current);
      esRef.current?.close();
    };
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logLines]);

  async function startRun() {
    setSubmitting(true);
    setLogLines([]);
    try {
      const doc = docUrls.trim();
      const isDemo = doc === "" || doc.startsWith("examples/");
      const res = await fetch("/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode,
          subject_name: subjectName,
          packet_path: isDemo
            ? (doc || (mode === "ma" ? "examples/tprm/hashicorp" : "examples/tprm/acme"))
            : undefined,
          drive_folder_url: !isDemo ? doc : undefined,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? "Server error");
      }
      const { run_id } = await res.json();
      const pipeline = mode === "ma" ? MA_PIPELINE : VENDOR_PIPELINE;
      const initialState: RunState = {
        runId: run_id, phase: "running", mode,
        subject: subjectName, pipeline,
        completedNodes: [], nodeLabels: { ...NODE_LABELS },
        verdict: null, error: null, elapsedSec: 0,
      };
      setRunState(initialState);

      const startTime = Date.now();
      timerRef.current = setInterval(() => {
        setRunState((prev) => prev
          ? { ...prev, elapsedSec: Math.floor((Date.now() - startTime) / 1000) }
          : prev);
      }, 1000);

      const es = new EventSource(`/events/${run_id}`);
      esRef.current = es;
      const streamTerminated = { current: false };

      es.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.type === "done") {
            streamTerminated.current = true;
            timerRef.current && clearInterval(timerRef.current!);
            es.close();
            setRunState((prev) => prev ? { ...prev, phase: "done" } : prev);
            return;
          }
          if (msg.type === "error") {
            streamTerminated.current = true;
            timerRef.current && clearInterval(timerRef.current!);
            es.close();
            setRunState((prev) => prev ? { ...prev, phase: "error", error: msg.message } : prev);
            return;
          }
          if (msg.type === "log") {
            setLogLines((prev) => [
              ...prev,
              { text: msg.message ?? msg.text ?? "", level: msg.level ?? "info" },
            ]);
            return;
          }
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
              default:
                return prev;
            }
          });
        } catch {}
      };

      es.onerror = () => {
        if (streamTerminated.current) { es.close(); return; }
        streamTerminated.current = true;
        timerRef.current && clearInterval(timerRef.current!);
        setRunState((prev) => {
          if (!prev || prev.phase === "done" || prev.phase === "error") return prev;
          return { ...prev, phase: "error", error: "Connection lost" };
        });
        es.close();
      };
    } catch (err) {
      setRunState((prev) => prev
        ? { ...prev, phase: "error", error: String(err) }
        : {
            runId: "", phase: "error", mode, subject: subjectName,
            pipeline: [], completedNodes: [], nodeLabels: {},
            verdict: null, error: String(err), elapsedSec: 0,
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
    setLogLines([]);
  }

  const rs = runState;
  const isRunDisabled = submitting || !subjectName;

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", display: "flex", flexDirection: "column" }}>

      {/* Zone 1 — Command Bar */}
      <CommandBar runState={rs} onNewRun={reset} />

      {/* Zone 2 — Pipeline Timeline (only when a run is active) */}
      {rs && (
        <PipelineTimeline
          mode={rs.mode}
          completedNodes={rs.completedNodes}
          phase={rs.phase}
        />
      )}

      {/* Zone 3 — Canvas */}
      {!rs ? (

        /* ── Idle: centred scoping form ── */
        <div
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "32px 16px",
          }}
        >
          <div
            style={{
              width: "100%",
              maxWidth: 420,
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              borderRadius: var(--radius-md),
              padding: "28px 24px",
            }}
          >
            <h2 style={{ margin: "0 0 4px", fontSize: 16, fontWeight: 600, fontFamily: "'Google Sans', 'Roboto', sans-serif", color: "var(--text-primary)" }}>
              New Analysis
            </h2>
            <p style={{ margin: "0 0 24px", fontSize: 13, color: "var(--text-secondary)", fontFamily: "'Google Sans', 'Roboto', sans-serif" }}>
              Vendor due diligence or M&amp;A assessment in ~60 seconds.
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div>
                <label htmlFor="subject-name">Company Name</label>
                <input
                  id="subject-name"
                  type="text"
                  value={subjectName}
                  onChange={(e) => setSubjectName(e.target.value)}
                  placeholder="e.g. Acme Cloud Analytics"
                />
              </div>

              <div>
                <label htmlFor="mode-select">Assessment Mode</label>
                <select
                  id="mode-select"
                  value={mode}
                  onChange={(e) => setMode(e.target.value as Mode)}
                >
                  <option value="vendor">Vendor Due Diligence</option>
                  <option value="ma">M&amp;A Due Diligence</option>
                </select>
              </div>

              <div>
                <label htmlFor="doc-urls">Document URLs</label>
                <textarea
                  id="doc-urls"
                  value={docUrls}
                  onChange={(e) => setDocUrls(e.target.value)}
                  placeholder={"https://drive.google.com/drive/folders/…\n\nLeave blank to use demo packet."}
                  rows={3}
                />
                <div style={{ marginTop: 6, display: "flex", gap: 12 }}>
                  <button
                    type="button"
                    onClick={() => { setSubjectName("Acme Cloud Analytics"); setMode("vendor"); setDocUrls("examples/tprm/acme"); }}
                    style={{ background: "none", border: "none", padding: 0, color: "var(--accent)", fontSize: 11, fontFamily: "'Google Sans', 'Roboto', sans-serif", cursor: "pointer", textDecoration: "underline" }}
                  >
                    Load vendor demo
                  </button>
                  <button
                    type="button"
                    onClick={() => { setSubjectName("HashiCorp Inc."); setMode("ma"); setDocUrls("examples/tprm/hashicorp"); }}
                    style={{ background: "none", border: "none", padding: 0, color: "var(--accent)", fontSize: 11, fontFamily: "'Google Sans', 'Roboto', sans-serif", cursor: "pointer", textDecoration: "underline" }}
                  >
                    Load M&amp;A demo
                  </button>
                </div>
              </div>

              <button
                onClick={startRun}
                disabled={isRunDisabled}
                style={{
                  background: "#ffffff",
                  color: "#000000",
                  padding: "12px",
                  fontSize: 14,
                  fontWeight: 600,
                  fontFamily: "'Google Sans', 'Roboto', sans-serif",
                  borderRadius: 8,
                  border: "none",
                  width: "100%",
                  marginTop: 4,
                  opacity: isRunDisabled ? 0.38 : 1,
                  cursor: isRunDisabled ? "not-allowed" : "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 8,
                }}
              >
                {submitting ? (
                  <>
                    <span
                      style={{
                        width: 14, height: 14,
                        border: "2px solid rgba(0,0,0,0.2)",
                        borderTopColor: "#000000",
                        borderRadius: "50%",
                        display: "inline-block",
                        animation: "spin 700ms linear infinite",
                      }}
                    />
                    Starting…
                  </>
                ) : "Run Analysis →"}
              </button>
            </div>
          </div>
        </div>

      ) : (

        /* ── Active run: split canvas ── */
        <div style={{ flex: 1, display: "flex", minHeight: 0, overflow: "hidden" }}>

          {/* Left — Live Log */}
          <div
            style={{
              flex: 1,
              borderRight: "1px solid rgba(255,255,255,0.07)",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                padding: "10px 16px",
                borderBottom: "1px solid var(--border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexShrink: 0,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                {rs.phase === "running" && (
                  <span
                    style={{
                      width: 6, height: 6, borderRadius: "50%",
                      background: "var(--accent)",
                      display: "inline-block",
                      animation: "pulse 1.4s ease-in-out infinite",
                    }}
                  />
                )}
                <span
                  style={{
                    fontFamily: "'Google Sans', 'Roboto', sans-serif",
                    fontSize: 11, fontWeight: 500,
                    color: "var(--text-secondary)",
                    textTransform: "uppercase",
                    letterSpacing: "0.08em",
                  }}
                >
                  Live Output
                </span>
              </div>
              <span style={{ fontFamily: "'Roboto Mono', monospace", fontSize: 11, color: "var(--text-secondary)" }}>
                {fmtDuration(rs.elapsedSec)}
              </span>
            </div>

            <div
              style={{
                flex: 1, overflowY: "auto",
                padding: "8px 16px",
                fontFamily: "'Roboto Mono', monospace",
                fontSize: 11, lineHeight: 1.6,
              }}
            >
              {logLines.length === 0 && rs.phase === "running" && (
                <div style={{ color: "var(--text-muted)" }}>
                  {rs.completedNodes.length} / {rs.pipeline.length} stages complete…
                </div>
              )}
              {logLines.map((line, i) => (
                <div
                  key={i}
                  style={{
                    color: line.level === "error" ? "#ea4335"
                         : line.level === "warn"  ? "#fa7b17"
                         : "var(--text-secondary)",
                  }}
                >
                  {line.text}
                </div>
              ))}
              {rs.phase === "running" && (
                <span
                  style={{
                    display: "inline-block",
                    width: 7, height: 13,
                    background: "var(--text-secondary)",
                    verticalAlign: "text-bottom",
                    animation: "blink-cursor 1s step-end infinite",
                    marginLeft: 1,
                  }}
                />
              )}
              <div ref={logEndRef} />
            </div>
          </div>

          {/* Right — Verdict + Findings */}
          <div
            style={{
              flex: 1,
              overflowY: "auto",
              padding: 16,
              display: "flex",
              flexDirection: "column",
              gap: 16,
            }}
          >
            <div
              style={{
                fontSize: 11,
                fontFamily: "'Google Sans', 'Roboto', sans-serif",
                fontWeight: 500,
                color: "var(--text-secondary)",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
              }}
            >
              Analysis
            </div>

            {rs.phase === "running" && !rs.verdict && (
              <div
                role="status"
                aria-live="polite"
                style={{
                  flex: 1, display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 12,
                }}
              >
                <div
                  style={{
                    width: 32, height: 32,
                    border: "2px solid var(--border)",
                    borderTopColor: "var(--accent)",
                    borderRadius: "50%",
                    animation: "spin 800ms linear infinite",
                  }}
                />
                <span style={{ fontFamily: "'Google Sans', 'Roboto', sans-serif", fontSize: 13, color: "var(--text-secondary)" }}>
                  {rs.completedNodes.length} / {rs.pipeline.length} stages
                </span>
              </div>
            )}

            {rs.verdict && <VerdictCard data={rs.verdict} mode={rs.mode} />}
            {rs.verdict?.ic_memo && rs.mode === "ma" && <ICMemoSection memo={rs.verdict.ic_memo} />}
            {rs.verdict?.pmi_plan && rs.mode === "ma" && <PMIPlanSection plan={rs.verdict.pmi_plan} />}

            {rs.phase === "error" && (
              <div
                style={{
                  background: "rgba(234,67,53,0.08)",
                  border: "1px solid rgba(234,67,53,0.25)",
                  borderRadius: 10,
                  padding: 16,
                  display: "flex",
                  gap: 10,
                }}
              >
                <span style={{ fontSize: 14, color: "var(--sev-critical)", lineHeight: 1.35, flexShrink: 0 }}>⚠</span>
                <div>
                  <div style={{ fontWeight: 500, fontSize: 14, color: "var(--sev-critical)", marginBottom: 4, fontFamily: "'Google Sans', 'Roboto', sans-serif" }}>
                    Assessment Failed
                  </div>
                  <p style={{ fontFamily: "'Roboto Mono', monospace", fontSize: 12, color: "var(--text-primary)", margin: 0 }}>
                    {rs.error}
                  </p>
                  <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "8px 0 0", fontFamily: "'Google Sans', 'Roboto', sans-serif" }}>
                    Check that your Google Drive folder is shared with the service account, then click + New Run to retry.
                  </p>
                </div>
              </div>
            )}
          </div>

        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Fix the `borderRadius` template literal in the scoping form**

The line:
```tsx
borderRadius: var(--radius-md),
```
is a bug — it must be a string. Change it to:
```tsx
borderRadius: "var(--radius-md)",
```

- [ ] **Step 4: Run TypeScript check**
```bash
cd Orchestra/dashboard && npx tsc --noEmit 2>&1
```
Expected: zero errors. Common issues and fixes:
- `Cannot find name 'React'` → add `import React from "react";` at top of file (already present as `import { useState, ... }` — change to `import React, { useState, ... }`)
- Any remaining reference to removed state (`maScope`, `scopingComplete`, `packetPath`, `sourceType`, `driveFolderUrl`) → delete the reference

- [ ] **Step 5: Commit**
```bash
git add Orchestra/dashboard/src/App.tsx
git commit -m "feat: B2 layout — CommandBar, PipelineTimeline, split canvas, centred scoping form"
```

---

### Task 7: Visual verify in dev server

**Files:** none

- [ ] **Step 1: Start backend + frontend**

Terminal 1 (from `Orchestra/`):
```bash
uvicorn orchestra_tprm.server.app:app --host 0.0.0.0 --port 8080
```

Terminal 2 (from `Orchestra/dashboard/`):
```bash
npm run dev
```

Open http://localhost:3000.

- [ ] **Step 2: Verify idle state**
- Background is pure black `#000`
- Command bar (top, ~48px): `#0c0c0c`, logo SVG + "Orchestra TPRM" wordmark left, "+ New Run" white button right
- No pipeline timeline visible (only appears during a run)
- Centred form card on black background: Company Name input, Assessment Mode dropdown, Document URLs textarea, "Run Analysis →" white button
- "Load vendor demo" and "Load M&A demo" underlined links below textarea

- [ ] **Step 3: Load vendor demo + run**
Click "Load vendor demo" → fields populate (Acme Cloud Analytics, Vendor Due Diligence, `examples/tprm/acme`) → click "Run Analysis →".
Verify:
- Pipeline timeline appears below command bar: Intake → Specialists → Policy → Coordinator
- Intake node active (pulsing white dot in circle)
- Command bar centre pill shows "Acme Cloud Analytics · Vendor Assessment · ● running"
- Left column header: `● LIVE OUTPUT` with elapsed timer (Roboto Mono)
- Left column body: "0 / N stages complete…" in Roboto Mono + blinking cursor
- Right column header: "ANALYSIS", shows spinner with stage count
- As nodes complete: circle fills white with black checkmark, connector brightens
- On `verdict` SSE event: VerdictCard appears in right column
- On `done` event: pill switches to "complete · Xs" in green Roboto Mono

- [ ] **Step 4: Load M&A demo + run**
Click "+ New Run" → load M&A demo → run. Verify:
- Timeline shows 6 nodes: Intake → VDR Gate → Specialists → Policy → Coordinator → PMI Plan
- ICMemoSection and PMIPlanSection appear after verdict (M&A only)

- [ ] **Step 5: Commit**
```bash
git add -A
git commit -m "chore: B2 redesign verified — visual QA pass"
```

---

### Task 8: Build verify + success criteria check

- [ ] **Step 1: Production build**
```bash
cd Orchestra/dashboard && npm run build 2>&1
```
Expected: `dist/` created, no TypeScript errors, no Vite build errors.

- [ ] **Step 2: Verify zero MD3 vars remain**
```powershell
Select-String -Path "Orchestra\dashboard\src\App.tsx", "Orchestra\dashboard\src\index.css" -Pattern "md-sys-color"
```
Expected: no output.

- [ ] **Step 3: Verify REJECT/APPROVE font**
In the running app, trigger a run to completion. In browser DevTools, inspect the verdict label text (e.g. "APPROVE"). Confirm `font-family` computes to `Roboto Mono`. The `VerdictCard` badge uses `fontSize: 12, fontWeight: 500` — verify it uses Roboto Mono by adding it explicitly if missing: change the verdict label `<span>` to include `fontFamily: "'Roboto Mono', monospace"`.

- [ ] **Step 4: Final commit**
```bash
git add Orchestra/dashboard/src
git commit -m "chore: B2 redesign complete — build clean, zero MD3 vars, success criteria met"
```

---

## Notes

- **`ma_scope` removed from POST body**: The new simplified form does not collect M&A deal-scoping fields. The backend uses defaults. If M&A runs fail due to missing `ma_scope`, add `ma_scope: mode === "ma" ? { investment_thesis: "", deal_breakers: [], active_workstreams: ["legal","financial","tech","commercial","hr","esg","regulatory"] } : undefined` back to the fetch body in `startRun`.
- **Arc gauge in VerdictCard**: The spec mentions an SVG arc gauge but the current VerdictCard uses a numeric risk score. Not added — structural VerdictCard change is out of spec scope ("only visual tokens applied").
- **History button**: Omitted — no history storage exists in the app (YAGNI).
