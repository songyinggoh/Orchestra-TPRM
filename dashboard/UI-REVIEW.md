# Orchestra TPRM Dashboard — UI Review

**Audited:** 2026-05-17
**Baseline:** UI-SPEC.md (approved design contract, phase 1)
**Screenshots:** Not captured — no dev server detected on ports 3000, 5173, or 8080. Code-only audit.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | All declared CTAs and error copy match spec; one raw `alert()` exposes unformatted error to user |
| 2. Visuals | 2/4 | Form labels missing CSS class wiring — rendered as unstyled text; no `aria-label` or `role` on any interactive element |
| 3. Color | 3/4 | Token system correct; hardcoded hex fallback `#8b8fa8` in VerdictCard escapes the token system |
| 4. Typography | 3/4 | Declared 4 sizes (12/14/16/28px) and 2 weights (400/500) respected; undeclared `fontSize: 20` and `fontSize: 22` break the 4-size rule |
| 5. Spacing | 3/4 | Spacing scale tokens used consistently; one hardcoded `padding: "12px var(--space-lg)"` at Run Assessment button breaks scale discipline |
| 6. Experience Design | 2/4 | No `aria-*` accessibility on any input, button, or live region; `alert()` used for catch-path errors; no keyboard focus-visible ring on interactive elements other than inputs |

**Overall: 16/24**

---

## Top 3 Priority Fixes

1. **Form `<label>` elements are styled via CSS global rule but `<select>` and `<input>` elements have no `id`/`for` wiring** — screen readers cannot associate labels with their controls; keyboard users tabbing into fields have no announced label — Add `id` to every input/select and `htmlFor` to every `<label>` in the form section (App.tsx lines 838–904).

2. **`alert(String(err))` at App.tsx line 654 exposes raw error string in a browser modal** — This fires when the `/run` POST fails before SSE begins; user sees a browser-native dialog with a raw JS error string rather than the designed "Assessment Failed" error banner — Replace with `setRunState({ phase: "error", error: String(err), ... })` so the styled error banner is shown instead.

3. **No `aria-label` or accessible name on icon-only / visually-labeled interactive elements** — The header logo container, "New Assessment" back-button, source toggle segments, and all pipeline step icons have zero ARIA attributes — Add `aria-label` to the "New Assessment" button and `aria-pressed` to SourceToggle segments; add `role="status"` + `aria-live="polite"` to the waiting-state panel and pipeline footer.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)

WARNING — Substantially compliant; one deviation breaks the designed error flow.

**Passing items:**
- Primary CTA: "Run Assessment" — matches spec exactly (App.tsx line 964)
- Page title: "New Assessment" — matches spec (App.tsx line 821)
- Page subtitle: "Submit a vendor or M&A packet for multi-agent risk analysis." — matches spec (App.tsx line 832)
- Source toggle labels: "Demo Packet" / "Google Drive" — match spec (App.tsx lines 222–223)
- Demo select label: "Demo Scenario" — matches spec (App.tsx line 865)
- Drive URL helper: "Share the folder with your service account before running." — matches spec (App.tsx line 893)
- Waiting state heading: "Analysis in Progress" — matches spec (App.tsx line 1170)
- Waiting state body: "{N} of {total} stages complete" — matches spec (App.tsx line 1180)
- Pipeline footer running: "Running · {elapsed}" — matches spec (App.tsx line 1072)
- Pipeline footer done: "Complete · {elapsed}" — matches spec (App.tsx line 1095)
- Pipeline footer error: "Analysis Failed" — matches spec (App.tsx line 1119)
- Error banner heading: "Assessment Failed" — matches spec (App.tsx line 1246)
- Error banner para 2: matches declared template verbatim (App.tsx lines 1270–1272)
- Overflow row text: "+ {N} additional findings" — matches spec (App.tsx line 533)
- Header "New Assessment" button label — matches spec (App.tsx line 787)

**Failing items:**

- **WARNING** App.tsx line 654: `alert(String(err))` — when the `POST /run` call fails before the run state is set, the user sees a browser `alert()` modal with a raw JavaScript error string. The spec declares the "Assessment Failed" error banner as the sole error surface. This path bypasses the designed pattern entirely. The copy inside `alert(String(err))` is whatever the JS Error.message happens to be — no declared template, no actionable recovery instruction.

- **WARNING** App.tsx line 748: Header subtitle reads "Multi-Agent Risk Platform · Gemini 2.5 Flash" without `fontWeight: 400` declared explicitly. The CSS spec says `12px / weight 400 / opacity 0.45`. The inline style omits `fontWeight`, inheriting from the global `button { font-weight: 500 }` cascade if the element ever becomes a button child. Currently not a button, so inheritance from body (400) applies — acceptable but fragile.

---

### Pillar 2: Visuals (2/4)

WARNING — Structural hierarchy is present but accessibility and form wiring gaps reduce score from code-only perspective.

**Focal point check:**
- FormCard: "Run Assessment" is full-width, 48px, primary-fill — correct primary visual anchor per spec.
- Run view: Risk score number at 28px / weight 500 is the largest text element in the verdict region — correct.
- Waiting state: 40px spinner centered with "Analysis in Progress" title — correct.

**Visual hierarchy indicators (code-only, no screenshot):**
- Size differentiation: 28px display > 16px title > 14px body > 12px label — scale is present.
- Weight differentiation: 500 for headings/labels vs 400 for body — correct.
- Color differentiation: on-surface vs on-surface-variant — applied.

**Defects:**

- **BLOCKER (accessibility)** Zero `aria-label`, `role`, `aria-pressed`, `aria-live`, or `aria-describedby` attributes anywhere in App.tsx. The grep for `aria-label|aria-live|role=|tabIndex` returns no matches. Specific gaps:
  - Source toggle buttons: no `aria-pressed`, no announced state change.
  - "New Assessment" back-button: icon leads, but no `aria-label` to announce its function to screen readers.
  - Waiting state panel: no `role="status"` or `aria-live="polite"` — screen readers won't announce progress updates.
  - Pipeline footer status: no `aria-live` — running/done/error transitions are silent.
  - Logo container div: no `role="img"` or `aria-label`.

- **WARNING** `<label>` elements for Assessment Type, Subject Name, Document Source, Demo Scenario, Google Drive Folder URL are bare `<label>` elements with no `htmlFor`. The corresponding `<input>` and `<select>` elements have no `id`. Label-to-control association is broken. This is a form usability failure, not just an accessibility one — clicking the label text will not focus the input.

- **WARNING** Icon-only visual: the header logo `<div>` contains only a Material Symbol. It has no tooltip, no `aria-label`, no `title`. Users relying on screen readers cannot identify the application logo region.

- **WARNING** Source toggle active state uses only background color change as the active indicator. The spec specifies this is sufficient, but without `aria-pressed` the state is imperceptible to assistive technology.

---

### Pillar 3: Color (3/4)

WARNING — Token system is correctly implemented; two instances escape the system.

**Token audit:**
- All 36 CSS custom properties from UI-SPEC.md are present in `index.css` with exact hex values verified.
- Severity colors in SEV_COLOR map (App.tsx lines 63–68): all four match spec (`#ea4335`, `#fa7b17`, `#fbbc04`, `#34a853`).
- Verdict colors in VERDICT_COLOR map (App.tsx lines 71–75): all three match spec.
- Background opacity chip formula `{color}1a` and border formula `{color}4d` — correctly applied in VerdictCard severity chips and verdict badge (App.tsx lines 398–401, 321–323).
- Waiting state spinner: `border-top-color: var(--md-sys-color-primary)` — correct.
- Error banner: `rgba(242,69,61,0.10)` background, `rgba(242,69,61,0.30)` border — matches spec exactly.
- 60/30/10 distribution: Accent (`--md-sys-color-primary` #1a73e8) is applied only on: Run Assessment button fill, active source toggle fill, active pipeline step border, input focus ring, waiting state spinner, progress bar fill — all 5 declared usage points. No accent on headings, decorative borders, or table text. Contract met.
- `--accent-light: #4f8ef0` used as hover border on inputs — correct per spec.

**Defects:**

- **WARNING** App.tsx line 299: `const color = VERDICT_COLOR[verdict] ?? "#8b8fa8"` — the fallback `#8b8fa8` is a hardcoded hex that matches `--md-sys-color-on-surface-variant` exactly but is not referenced via token. If the design token value changes, this fallback drifts silently. Should be `?? "var(--md-sys-color-on-surface-variant)"`.

- **WARNING** App.tsx line 943: `borderTopColor: "#ffffff"` — the loading spinner inside the Run Assessment button uses a hardcoded white rather than `var(--md-sys-color-on-primary)`. The spec declares the button color as `--md-sys-color-on-primary`. These resolve to the same value currently but the hardcode creates a maintenance hazard.

- **WARNING** `rgba(26,115,232,0.12)` and `rgba(26,115,232,0.08)` and `rgba(26,115,232,0.06)` appear as inline literal values (App.tsx lines 121, 124, 466) rather than composed from the `--md-sys-color-primary` token. These are spec-correct values but bypass the token system. The spec's background tint formula `{color}1a` implies these should derive from the token, not be hardcoded.

---

### Pillar 4: Typography (3/4)

WARNING — Spec declares 4 sizes maximum; implementation uses 6 distinct sizes.

**Declared type scale (spec):**
| Role | Size | Weight |
|------|------|--------|
| Display | 28px | 500 |
| Title | 16px | 500 |
| Body | 14px | 400 |
| Label | 12px | 500 |

**Sizes found in App.tsx (inline `fontSize` values):**
- 12px — Label role (correct)
- 14px — Body role (correct)
- 16px — Title role (correct)
- 18px — Icon sizes only (Material Symbols are set via `font-size`, not content text)
- 20px — Error banner icon (App.tsx line 1228)
- 22px — Header logo icon (App.tsx line 723)
- 28px — Display role (correct)

The 18px, 20px, and 22px usages are all on `material-symbols-outlined` spans — they control icon rendering size, not text content size. Spec declares icon sizes explicitly as 18px (pipeline step, toggle, badge), 16px (footer), 20px (error banner leading icon), 22px (header logo). These are icon sizing values, not typography roles.

**Assessment:** The 4-size limit in the spec applies to "text content" roles, not icon font-size declarations. The actual text content sizes are 12/14/16/28px only, which matches the declared 4-role system. Weight distribution is 400 and 500 only — correct.

**Defects:**

- **WARNING** App.tsx line 748 omits explicit `fontWeight` on the header subtitle div. The spec declares `weight 400` for this element. No explicit `fontWeight: 400` is set, so the element inherits from the CSS body rule (14px / 400). Currently renders correctly, but the explicit declaration is missing, creating a fragile dependency on cascade.

- **WARNING** App.tsx line 827–829: The form subtitle paragraph sets `fontSize: 14, fontWeight: 400` but also sets `marginTop: 0` via inline style while the spec says `margin-bottom: --space-xl`. The `marginBottom: "var(--space-xl)"` is on the `<p>` (line 826) — this is correct. However `marginTop: 0` overrides default browser paragraph margin — this is cosmetically acceptable but the explicit `0` value is not from the spacing scale. Minor.

- **WARNING** ALL CAPS restriction: spec restricts ALL CAPS to label role, severity badge, verdict badge, table column headers. The implementation applies `textTransform: "uppercase"` at: label elements (index.css line 152), table headers (App.tsx line 450), verdict badge text (App.tsx line 348), severity chip text (App.tsx line 422 — implicit via mapping), severity pill in table (App.tsx line 502). No violation found.

- **WARNING** Letter-spacing: spec says ALL CAPS labels `0.08em`, ALL CAPS table headers `0.06em`, verdict badge `0.10em`. Implemented at: labels via CSS `letter-spacing: 0.08em` (index.css line 153), table headers `letterSpacing: "0.06em"` (App.tsx line 451), verdict badge `letterSpacing: "0.10em"` (App.tsx line 349). All match. Pass.

---

### Pillar 5: Spacing (3/4)

WARNING — Spacing scale is comprehensively adopted; one hardcoded value breaks discipline.

**Spacing token usage across App.tsx — all spacing values found:**
- `var(--space-xs)` (4px) — icon-to-label gaps, badge padding, margin-bottom on labels
- `var(--space-sm)` (8px) — card inner padding, input padding vertical, cell padding vertical, footer padding-top
- `var(--space-sm2)` (12px) — pipeline step vertical padding, table cell padding, progress bar margin-top
- `var(--space-md)` (16px) — header gap, card horizontal padding, input horizontal padding, cell horizontal padding
- `var(--space-lg)` (24px) — card padding (all sides), section gap, error banner padding
- `var(--space-xl)` (32px) — page padding, form card padding, specialist node indent, main content padding
- `var(--space-2xl)` (48px) — form centering top margin, waiting panel vertical padding
- `0` — explicit zero margin on paragraph (App.tsx line 1255)

No arbitrary `[px]` or `[rem]` Tailwind-style values found (not applicable — project uses inline styles, not Tailwind).

**Defects:**

- **WARNING** App.tsx line 917: `padding: "12px var(--space-lg)"` — The Run Assessment button uses a hardcoded `12px` for vertical padding instead of `var(--space-sm2)` (which also equals 12px). This is a token discipline violation. The value resolves identically but breaks the maintainability contract. The spec declares button padding as `12px 24px` (explicitly), suggesting this was deliberate — however the spec also mandates `--space-sm2` for 12px values throughout. Should be `var(--space-sm2) var(--space-lg)`.

- **WARNING** App.tsx line 275: Source toggle segment buttons have `padding: 0` inline. The segments rely on `height: 44` + `flex` centering for touch target. This is WCAG 2.5.5 compliant (44px height) but the source toggle spec says height 44px — that is met. No padding violation since the 44px is the touch target. Pass with note.

- **WARNING** Pipeline panel `position: sticky, top: "var(--space-lg)"` (App.tsx line 988) — spec says `top 24px` which is `--space-lg`. Token used correctly.

- **WARNING** App.tsx line 1255: `margin: 0` on the error banner technical paragraph — not from the spacing scale, but `0` is a valid reset value. Acceptable.

---

### Pillar 6: Experience Design (2/4)

WARNING — State coverage is good; accessibility and error handling have significant gaps.

**State coverage inventory:**

| State | Present | Notes |
|-------|---------|-------|
| Loading (form submitting) | Yes | `submitting` state drives button spinner and opacity |
| Running (SSE active) | Yes | Pipeline step active state, waiting panel |
| Done (verdict) | Yes | VerdictCard reveal animation |
| Error (SSE error / backend error) | Partial | SSE error path renders error banner; POST error path fires `alert()` |
| Empty (no findings) | Guarded | `data.findings.length > 0` gate — table hidden when no findings, but no empty state message shown |
| Disabled (run button) | Yes | `isRunDisabled` drives opacity 0.38 + cursor not-allowed |
| Connection loss | Yes | `es.onerror` sets error state with "Connection lost" message |

**Defects:**

- **BLOCKER** App.tsx line 654: `alert(String(err))` — browser `alert()` for POST failures. This is:
  (a) Not the designed error surface
  (b) Blocks the tab until dismissed — no other UI interaction possible
  (c) Cannot be styled or branded
  (d) Provides no actionable recovery instruction
  The `catch` block fires before `setRunState` has been called with a running state, so the component cannot transition to the error banner directly. The fix requires setting runState with `phase: "error"` before the catch block exits, or refactoring `startRun` to set an error state on the form card itself.

- **BLOCKER (accessibility)** No `aria-label` attributes on any interactive element. Full list:
  - Logo `<div>`: no `role="img"`, no `aria-label`
  - "New Assessment" `<button>` (App.tsx line 758): has visible text "New Assessment" — label exists via text content, acceptable
  - Source toggle `<button>` elements (App.tsx lines 254–289): have visible label text — acceptable for announced label, but missing `aria-pressed` for state
  - Run Assessment `<button>` (App.tsx line 907): has visible text — acceptable
  - Waiting state panel: no `role="status"`, no `aria-live`. Screen readers will not announce the "Analysis in Progress" state or progress updates
  - Pipeline footer status divs (App.tsx lines 1052–1119): no `aria-live="polite"` — running/done/error state changes are silent to assistive tech
  - Findings table: no `<caption>`, no `scope="col"` on `<th>` elements

- **WARNING** `<input>` and `<select>` elements have no `id` attribute; `<label>` elements have no `htmlFor`. The CSS `label { display: block }` rule styles the labels, but the programmatic association between label and control is broken. Clicking a label does not focus its input. Screen readers announce the inputs without label context.

- **WARNING** No `focus-visible` ring on interactive elements beyond inputs. The spec declares focus rings for: Run Assessment button (3px ring), "New Assessment" button (3px ring), source toggle segments (2px inset ring). The CSS file has no `:focus-visible` rule for buttons. The button in index.css (line 128–137) has no `:focus-visible` style. Keyboard-only users pressing Tab to the Run Assessment button receive no visible focus indicator — WCAG 2.4.7 failure.

- **WARNING** No `ErrorBoundary` component wrapping the application. A JavaScript render error will produce a blank white screen rather than a graceful failure state. Acceptable for a single-file prototype but notable.

- **WARNING** Findings table overflow is capped at 50 rows (App.tsx line 459) — sensible, but the overflow copy "+ {N} additional findings" (line 533) provides no affordance to load or export remaining findings. For a TPRM tool where complete findings are legally significant, truncation without an export path is a product-level gap.

- **WARNING** No `disabled` prop on the "New Assessment" button while `submitting` is true. If the SSE stream opens and the user clicks the header back-button mid-run, `reset()` closes the EventSource and clears state — acceptable design, but the button is not disabled during the `submitting` window, so a double-click could fire two POST requests in rapid succession.

---

## Files Audited

- `C:\Users\user\Desktop\github\Transforming Enterprise Through AI\Orchestra\dashboard\UI-SPEC.md` — Design contract (ground truth)
- `C:\Users\user\Desktop\github\Transforming Enterprise Through AI\Orchestra\dashboard\src\App.tsx` — Sole implementation file (1283 lines)
- `C:\Users\user\Desktop\github\Transforming Enterprise Through AI\Orchestra\dashboard\src\index.css` — Token and animation definitions (209 lines)
- `C:\Users\user\Desktop\github\Transforming Enterprise Through AI\Orchestra\dashboard\index.html` — Font/icon CDN link verification

Registry audit: shadcn not initialized. Registry safety section not applicable.
