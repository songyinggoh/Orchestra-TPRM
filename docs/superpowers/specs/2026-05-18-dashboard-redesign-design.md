# Orchestra TPRM Dashboard Redesign

**Date:** 2026-05-18  
**Scope:** Visual redesign of the React dashboard (`Orchestra/dashboard/`)  
**Status:** Approved for implementation

---

## 1. Design System

### Color Tokens

| Token | Value | Usage |
|---|---|---|
| `--bg` | `#000000` | App background |
| `--surface-1` | `#0c0c0c` | Command bar, timeline bar |
| `--surface-2` | `#111111` | Cards, panels |
| `--surface-3` | `#141414` | Elevated inputs, hover states |
| `--border` | `rgba(255,255,255,0.08)` | All dividers and card borders |
| `--border-strong` | `rgba(255,255,255,0.14)` | Focused inputs, active cards |
| `--text-primary` | `#ffffff` | Headings, labels |
| `--text-secondary` | `rgba(255,255,255,0.45)` | Subtitles, metadata |
| `--text-muted` | `rgba(255,255,255,0.25)` | Placeholder, disabled |
| `--accent` | `#94a3c0` | Interactive elements, active pipeline nodes, progress |
| `--sev-critical` | `#ea4335` | Critical findings, REJECT verdict |
| `--sev-high` | `#fa7b17` | High findings |
| `--sev-medium` | `#fbbc04` | Medium findings |
| `--sev-low` | `#34a853` | Low findings, APPROVE verdict |

All existing MD3 CSS variables in `index.css` are replaced by this token set.

### Typography

| Role | Font | Weight |
|---|---|---|
| UI / body / labels | Google Sans | 400, 500, 600 |
| Verdict labels (`REJECT`, `APPROVE`, `REVIEW`) | Roboto Mono | 700 |
| Risk score number, elapsed timer, log stream | Roboto Mono | 400–700 |

Both fonts are already loaded via Google Fonts in `index.html`. No new font imports needed.

### Shape & Spacing

- Border radius: `8px` (inputs, log lines) · `10px` (cards) · `8px` (command bar pill)
- Card padding: `12px 14px`
- Section gap: `8px` between stacked elements, `14px` between major zones

---

## 2. Layout — B2: Command + Timeline

Single-page persistent layout. No full-screen navigation between states. Three stacked zones:

```
┌─────────────────────────────────────────────────────────┐
│  COMMAND BAR (48px)                                     │
├─────────────────────────────────────────────────────────┤
│  PIPELINE TIMELINE (56px)                               │
├────────────────────────┬────────────────────────────────┤
│  LIVE LOG              │  VERDICT + FINDINGS            │
│  (flex: 1)             │  (flex: 1)                     │
│                        │                                │
└────────────────────────┴────────────────────────────────┘
```

### Zone 1 — Command Bar

- Left: Orchestra logo (SVG) + wordmark "Orchestra TPRM"
- Centre: Active run pill — company name · mode · running status indicator (pulsing dot + "running" in Roboto Mono). Editable when idle (opens scoping form).
- Right: "History" ghost button · "+ New Run" filled white button (black text)

### Zone 2 — Pipeline Timeline

Horizontal step track. Nodes: **Intake → VDR Gate → 5 Specialists → Policy → Coordinator → PMI Plan**.

Node states:
- **Done** — filled white circle, black checkmark
- **Active** — white-bordered circle, pulsing white fill dot
- **Pending** — ghost circle (border only, low opacity)

Connectors are 1px lines that fade from full opacity (after done nodes) to low opacity (before pending nodes).

### Zone 3 — Split Canvas (two equal columns)

**Left — Live Log**

- Section label: `● LIVE OUTPUT` (pulsing dot) + elapsed timer (Roboto Mono, right-aligned)
- Log lines stream in via SSE, Roboto Mono 8.5px
- Colour coding: default `rgba(255,255,255,0.45)`, warnings `#fa7b17`, critical hits `#ea4335`, info/done lines `rgba(255,255,255,0.3)`
- Blinking block cursor at end of last line while active
- Vertical divider (`rgba(255,255,255,0.07)`) separates from right column

**Right — Verdict + Findings**

- Section label: `ANALYSIS`
- **Verdict card** (top):
  - SVG arc gauge — track `rgba(255,255,255,0.06)`, fill colour matches verdict (`#ea4335` reject / `#34a853` approve)
  - Risk score number — Roboto Mono 700, white
  - Verdict label — Roboto Mono 700, `font-size: 18px`, coloured by verdict
  - Subtitle — company · mode, Google Sans, muted
  - Stacked severity bar (5px height, segments proportional to finding counts)
  - Severity legend — critical / high / medium / low counts
- **Findings list** (below verdict card, scrollable):
  - Each finding: severity badge (coloured pill) + agent name + description
  - Background tint + border match severity colour at low opacity
  - Items fade in as SSE events arrive

---

## 3. Scoping State

When no run is active the layout is the same shell (command bar + empty timeline + split canvas) but the canvas shows a centred form instead of log/results:

- Company name input
- Mode dropdown (M&A Due Diligence / Vendor Assessment / etc.)
- Document URLs textarea
- "Run Analysis" button — filled white, black text, full-width

Timeline nodes are all ghost (pending) until the run starts.

---

## 4. Implementation Scope

### Files changed

| File | Change |
|---|---|
| `dashboard/src/index.css` | Replace all MD3 CSS variables with the new token set above. Keep Vite/Tailwind reset. |
| `dashboard/src/App.tsx` | Restructure layout to B2 zones. Replace all inline style values. Swap `ScopingScreen` to centred-form in canvas. Add horizontal `PipelineTimeline` component. Refactor `VerdictCard` to use Roboto Mono for verdict label. Wire log stream into left column. |
| `dashboard/index.html` | Verify Google Sans + Roboto Mono are both in the `<link>` import (already present — no change expected). |

### Out of scope

- No changes to backend, SSE protocol, or API routes
- No changes to `ICMemoSection` or `PMIPlanSection` content — only visual tokens applied
- No new dependencies — Vite + React 19 + TypeScript only

---

## 5. Success Criteria

- `index.css` has zero remaining `--md-sys-color-*` variables
- `App.tsx` has no hardcoded hex colours outside of the severity constants (`#ea4335` etc.) — all other colours use CSS variables
- REJECT / APPROVE text renders in Roboto Mono 700
- Pipeline timeline shows correct node state (done / active / pending) driven by existing SSE pipeline events (implementor to confirm exact event type names from `App.tsx` SSE handler)
- Scoping form renders centred in the canvas when `runState === 'idle'`
- Live log streams into left column as SSE `log` events arrive
- No regressions in SSE connection, run submission, or verdict display
