// Playwright demo recorder for the Orchestra TPRM submission video.
//
// Records a deterministic 1920x1080 walkthrough against the live Cloud Run
// URL (REPLAY_MODE=true serves replay JSONLs so the run completes in ~2s).
//
// Usage:
//   cd Orchestra
//   npx playwright install chromium   # one-time
//   node scripts/record_demo.mjs [acme|hashicorp]
//
// Output: docs/submission/demo.webm
// Convert to MP4 with ffmpeg:
//   ffmpeg -i docs/submission/demo.webm -c:v libx264 -crf 23 -preset slow docs/submission/demo.mp4
//
// To use against a local dev backend instead of Cloud Run:
//   DEMO_URL=http://localhost:8080 node scripts/record_demo.mjs

import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { mkdirSync } from "node:fs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, "..");
const outDir = resolve(repoRoot, "docs", "submission");
mkdirSync(outDir, { recursive: true });

const DEMO_URL = process.env.DEMO_URL || "https://orchestra-tprm-67479435861.us-central1.run.app";
const SCENARIO = (process.argv[2] || "acme").toLowerCase();

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function record() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: outDir, size: { width: 1920, height: 1080 } },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();

  console.log(`[record_demo] navigating to ${DEMO_URL}`);
  await page.goto(DEMO_URL, { waitUntil: "networkidle", timeout: 60_000 });

  // Pre-warm pause so judges can read the landing page
  await wait(2_500);

  if (SCENARIO === "hashicorp") {
    console.log("[record_demo] selecting HashiCorp scenario");
    await page.selectOption("#demo-scenario", "examples/tprm/hashicorp");
    await wait(1_500);
    // M&A flow shows a Scoping screen — fill minimum required fields if present.
    const thesisInput = page.locator('textarea[placeholder*="SaaS consolidation"]').first();
    if (await thesisInput.isVisible().catch(() => false)) {
      await thesisInput.fill("Acquire HashiCorp for cross-sell into enterprise infra portfolio.");
      await wait(800);
      // Confirm scoping to proceed
      const confirmBtn = page.getByRole("button", { name: /confirm|continue|proceed/i }).first();
      if (await confirmBtn.isVisible().catch(() => false)) {
        await confirmBtn.click();
        await wait(1_500);
      }
    }
  } else {
    console.log("[record_demo] using default Acme scenario");
    await page.selectOption("#demo-scenario", "examples/tprm/acme");
    await wait(1_500);
  }

  // Click Run Assessment
  console.log("[record_demo] clicking Run Assessment");
  await page.getByRole("button", { name: /run assessment/i }).click();

  // Wait for the run to complete — replay mode finishes in ~2-3s.
  // Use the SSE 'done' event indirectly: look for verdict / findings count rendering.
  // Generous timeout to account for cold-start.
  await page.waitForFunction(
    () => {
      const text = document.body.innerText || "";
      return /verdict|findings|risk score|remediation/i.test(text);
    },
    null,
    { timeout: 90_000 },
  );

  // Linger so viewers can read the verdict + findings
  console.log("[record_demo] verdict reached, lingering on results");
  await wait(2_500);

  // Scroll through the result sections at a comfortable reading pace
  await page.evaluate(() => window.scrollTo({ top: 600, behavior: "smooth" }));
  await wait(3_500);
  await page.evaluate(() => window.scrollTo({ top: 1400, behavior: "smooth" }));
  await wait(3_500);
  await page.evaluate(() => window.scrollTo({ top: 2400, behavior: "smooth" }));
  await wait(3_500);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await wait(1_500);

  // Finish recording
  await context.close();
  await browser.close();

  console.log(`[record_demo] recording saved under ${outDir}`);
}

record().catch((err) => {
  console.error("[record_demo] failed:", err);
  process.exit(1);
});
