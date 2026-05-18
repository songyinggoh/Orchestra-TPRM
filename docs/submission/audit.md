# Submission Audit — 2026-05-19

Cross-checked against lablab.ai's [Submission Guide](https://lablab.ai/delivering-your-hackathon-solution).

## 1. Basic Information

| Field | Status | Source |
|---|---|---|
| Project Title | ✅ | `form.md` — *Orchestra — Multi-Agent Third-Party Risk Review on Google Gemini* |
| Short description (≤255 chars) | ✅ | `form.md` — 248 chars |
| Long description (≥100 words) | ✅ | `form.md` — ~340 words / ~2200 chars |
| Technology tags | ✅ | gemini, google-ai-studio, python, fastapi, react, cloud-run, bigquery, multi-agent, langgraph-alternative, sse |
| Category tags | ✅ | enterprise, risk-management, compliance, agents, due-diligence |

## 2. Cover Image & Presentation

| Field | Status | Source |
|---|---|---|
| Cover image — PNG/JPG, 16:9 | ✅ | `docs/submission/cover.png` — 1920×1080 PNG |
| Video — ≤5 min MP4 | ⏳ | Auto-recording in progress (~165s narrated walkthrough → MP4 via ffmpeg mux) |
| Slide deck — PDF | ✅ | `docs/submission/slides.pdf` — 14 slides, Marp render |

## 3. Application Hosting & Code Repository

| Field | Status | Source |
|---|---|---|
| Public GitHub repo | ✅ | `https://github.com/songyinggoh/Orchestra` — public, Apache-2.0, 14 topic tags |
| Repo description + homepage | ✅ | Set via `gh repo edit` — points at Cloud Run URL |
| IBM Bob Report | N/A | Track 2 (Google AI Studio); no IBM Bob involvement |
| Demo platform | ⚠️ | Cloud Run (lablab "opt for" lists Streamlit/Replit/Vercel — non-strict). Functional equivalent; surfaced in `form.md` |
| Application URL | ✅ | `https://orchestra-tprm-67479435861.us-central1.run.app` — `/health` 200, `REPLAY_MODE=true` |

## 4. Pro Tips Coverage

| Tip | Where covered |
|---|---|
| Highlight Problem & Solution | Slides 2-3 |
| Detail your Product | Slides 4-5 (architecture, pipeline) |
| Showcase User Interaction | Live demo URL + recorded video |
| Discuss Market Scope (TAM/SAM) | Slide 14 — $34B GRC + $18B due-diligence services, SAM $4B |
| Revenue Streams | Slide 14 — OSS framework + SaaS + enterprise tier |
| Analyze Competitors | Slide 13 — LangGraph / CrewAI comparison table |
| Future Prospects | Slide 15 — sanctions, privacy, ServiceNow, Jira roadmap |
| Brevity (2-3 sentences per slide) | All 14 slides comply |

## 5. Judging Criteria Coverage

| Criterion | Strongest evidence |
|---|---|
| Presentation | Slides + cover + narrated video |
| Business Value | Slides 2-3, 14 (problem framing + TAM/SAM + revenue) |
| Application of Technology | Slides 4-12 (architecture, pipeline, 3 spotlights), README, code |
| Originality | 3-agent delta (Risk Scoring, Remediation, ESG) spotlighted on slides 10-12; differentiates from LangGraph/CrewAI |

## 6. Submission Checklist

- [x] Project Title
- [x] Short and Long Descriptions
- [x] Technology and Category Tags
- [x] Cover Image
- [ ] Video Presentation *(generating)*
- [x] Slide Presentation
- [x] GitHub Repository
- [x] Application URL

## Security & Hygiene

| Check | Result |
|---|---|
| Public repo visibility | PUBLIC ✓ |
| License | Apache-2.0 ✓ |
| `.env` tracked? | NO — outer-dir only, never staged |
| Secret scan (`AIza…`, `sk-…`, `ghp_…`) | clean across 599 tracked files |
| Tracked sensitive paths | only template/source: `deploy/helm/.../secret.yaml`, `serviceaccount.yaml`, `src/orchestra/security/secrets.py` (no values) |
| Open issues / PRs blocking review | none |
| Branch sync | `origin/master` up-to-date, 17 commits on the 3-agent delta + audit |

## Remaining open items

1. **Video** — `scripts/record_demo.mjs` recording in background against the deterministic Cloud Run demo. Final step is `ffmpeg` mux of `narration.mp3` over the recorded WebM. ETA ~3 min from now.
2. **Form submission** — manual. Paste from `form.md`, attach `cover.png` + `slides.pdf` + `demo.mp4`. Deadline 2026-05-19 06:00 SGT (target) / 08:00 (hard).
