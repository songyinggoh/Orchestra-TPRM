---
name: project-orchestra-dashboard-ui
description: Orchestra TPRM dashboard — UI design system, conventions, and component architecture
metadata:
  type: project
---

# Orchestra TPRM Dashboard UI

**Stack**: React 19 + Vite + TypeScript SPA. Pure CSS custom properties + React inline styles. No component libraries, no Tailwind, no shadcn.

**Design system**: Google Material Design 3 dark scheme. Full MD3 token set in `src/index.css` (prefixed `--md-sys-color-*`, `--md-sys-elevation-*`, `--md-sys-shape-*`). Legacy bridge aliases (`--bg`, `--surface`, `--accent`, etc.) kept for backward compatibility.

**Fonts**: Roboto (300/400/500/700) via Google Fonts CDN. Material Symbols Outlined variable font via Google Fonts CDN. Both loaded in `index.html` `<head>` with preconnect tags. Icon usage: `<span className="material-symbols-outlined">icon_name</span>`. Font variation controlled via `fontVariationSettings` inline style (`'FILL' 1` for filled, `'FILL' 0` for outlined).

**Primary color**: `#1a73e8` (Google Blue). Reserved strictly for: Run Assessment button fill, active SourceToggle fill, active pipeline step left-border, input focus ring. NOT for headings or decoration.

**Severity palette** (Google exact):
- Critical: `#ea4335`, High: `#fa7b17`, Medium: `#fbbc04`, Low: `#34a853`

**Verdict palette**: Approve `#34a853`, Conditional `#fbbc04`, Reject `#ea4335`

**Chip/badge color formula**: background `{color}1a` (10% alpha), border `{color}4d` (30% alpha)

**Spacing scale**: `--space-xs` 4px through `--space-3xl` 64px. All multiples of 4px. Exception: `--space-sm2: 12px` approved midpoint for PipelineStep vertical rhythm.

**Component architecture**: All components hand-rolled. Key components: `PipelineStep`, `SourceToggle`, `VerdictCard` (with FindingsTable inlined). `App.tsx` holds all state; no external state library.

**Animation contracts**:
- `spin` keyframe → pipeline active step (900ms), waiting panel spinner (800ms), button loading (700ms)
- `step-check-in` keyframe → done icon appear (300ms, scale 0.5→1.2→1)
- `verdict-reveal` keyframe → VerdictCard mount (350ms, translateY 16px→0)
- All animations respect `prefers-reduced-motion` via media query in `index.css`

**Pipeline sidebar**: 260px fixed width. Specialist nodes (`LegalAgent`, `SecurityAgent`, `ExternalAgent`, `CodeAgent`, `FinancialAgent`) indented `--space-xl` (32px). State transitions: pending (opacity 0.40 icon) → active (spinning `autorenew`, primary bg tint 8%) → done (`check_circle`, green, 12% bg tint).

**Copy conventions**: "stages" not "nodes", "New Assessment" not "New Run", "Assessment Failed" not "Run failed", "+ {N} additional findings" not "more findings". See UI-SPEC.md copywriting contract section for full list.

**Why**: Phase 1 UI redesign to Google Material Design 3 dark scheme for procurement/M&A analyst personas (non-technical enterprise users).

**How to apply**: When modifying this dashboard, always consult `UI-SPEC.md` as source of truth. Keep legacy alias tokens in `:root` until all inline styles migrate to `--md-sys-*` tokens. Never introduce new npm packages — pure CSS + React inline styles constraint is intentional.
