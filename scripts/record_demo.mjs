// Playwright demo recorder synced to narration_timing.json.
//
// Reads docs/submission/narration_timing.json to learn each scene's start/end
// time, then drives the live Cloud Run URL with timed pauses that match
// the voiceover boundaries. After recording, mux the audio with ffmpeg:
//
//   FFMPEG=$(node -e "console.log(require('ffmpeg-static'))")
//   "$FFMPEG" -i docs/submission/page@*.webm -i docs/submission/narration.mp3 \
//     -c:v libx264 -crf 22 -preset medium -pix_fmt yuv420p \
//     -c:a aac -b:a 192k -shortest -movflags +faststart \
//     docs/submission/demo.mp4 -y
//
// Scene timeline (from narration_timing.json):
//   intro    0.0 → 18.7s   linger on slide-style landing (logo + headline)
//   landing 19.3 → 35.6s   show scenario dropdown + scope
//   pipeline 36.2 → 73.4s  click Run; watch NodeCards complete
//   results 74.0 → 113.1s  linger on risk score + findings + remediation
//   why    113.7 → ~145s   linger on completed dashboard (calm)
//   close  146 → 165s      return to top, fade
//
// Usage:
//   cd Orchestra/scripts
//   node record_demo.mjs            (default scenario: acme)

import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { mkdirSync, readFileSync } from "node:fs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, "..");
const outDir = resolve(repoRoot, "docs", "submission");
mkdirSync(outDir, { recursive: true });

const DEMO_URL = process.env.DEMO_URL || "https://orchestra-tprm-67479435861.us-central1.run.app";
const SCENARIO = (process.argv[2] || "acme").toLowerCase();

const wait = (ms) => new Promise((r) => setTimeout(r, Math.max(0, ms)));

const timingPath = resolve(outDir, "narration_timing.json");
let timing;
try {
  timing = JSON.parse(readFileSync(timingPath, "utf-8"));
} catch (err) {
  console.error("[record_demo] narration_timing.json not found — run generate_narration_gtts.py first.");
  process.exit(1);
}

const scenesById = Object.fromEntries(timing.scenes.map((s) => [s.id, s]));
const totalMs = timing.total_s * 1000 + 1000; // small tail buffer

async function lingerUntil(scenes, label) {
  const target = scenesById[label];
  if (!target) {
    console.warn(`[record_demo] unknown scene ${label}`);
    return;
  }
  const targetMs = target.end_s * 1000;
  const now = Date.now() - scenes.t0;
  await wait(targetMs - now);
}

async function record() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: outDir, size: { width: 1920, height: 1080 } },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  const scenes = { t0: 0 };

  console.log(`[record_demo] target total: ${(totalMs / 1000).toFixed(1)}s`);
  console.log(`[record_demo] navigating to ${DEMO_URL}`);

  await page.goto(DEMO_URL, { waitUntil: "networkidle", timeout: 60_000 });

  // ---- t = 0 ----------------------------------------------------------------
  scenes.t0 = Date.now();
  console.log("[record_demo] scene: intro");

  // Pre-warm. Just dwell on the landing so the intro voiceover can play
  // over the dashboard header.
  await lingerUntil(scenes, "intro");

  // ---- t ≈ 19s --------------------------------------------------------------
  console.log("[record_demo] scene: landing (pick scenario)");
  // Open the dropdown briefly to draw attention, then pick Acme
  await page.click("#demo-scenario");
  await wait(700);
  await page.selectOption("#demo-scenario", "examples/tprm/acme");
  await lingerUntil(scenes, "landing");

  // ---- t ≈ 36s --------------------------------------------------------------
  console.log("[record_demo] scene: pipeline (click Run)");
  await page.getByRole("button", { name: /run assessment/i }).click();
  // Wait for the verdict / findings to render (replay completes in ~2-3s
  // with REPLAY_MODE; networkidle is unreliable due to SSE).
  await page.waitForFunction(
    () => /verdict|findings|risk score|remediation/i.test(document.body.innerText || ""),
    null,
    { timeout: 60_000 },
  );
  await lingerUntil(scenes, "pipeline");

  // ---- t ≈ 73s --------------------------------------------------------------
  console.log("[record_demo] scene: results (scroll through outputs)");
  // Risk score hero first
  await page.evaluate(() => window.scrollTo({ top: 400, behavior: "smooth" }));
  await wait(6_000);
  // Findings table next
  await page.evaluate(() => window.scrollTo({ top: 1100, behavior: "smooth" }));
  await wait(8_000);
  // Remediation roadmap
  await page.evaluate(() => window.scrollTo({ top: 1800, behavior: "smooth" }));
  await wait(8_000);
  // ICMemo / coordinator section (if present)
  await page.evaluate(() => window.scrollTo({ top: 2500, behavior: "smooth" }));
  await lingerUntil(scenes, "results");

  // ---- t ≈ 113s -------------------------------------------------------------
  console.log("[record_demo] scene: why (linger on complete dashboard)");
  // Return to top for the framework-pitch section so viewers see the
  // verdict banner one more time.
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await lingerUntil(scenes, "why");

  // ---- t ≈ 146s -------------------------------------------------------------
  console.log("[record_demo] scene: close (final shot)");
  await lingerUntil(scenes, "close");

  // Small tail buffer
  await wait(500);

  await context.close();
  await browser.close();
  console.log(`[record_demo] recording saved under ${outDir}`);
}

record().catch((err) => {
  console.error("[record_demo] failed:", err);
  process.exit(1);
});
