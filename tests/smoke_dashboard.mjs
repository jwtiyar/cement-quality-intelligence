#!/usr/bin/env node
/**
 * Browser smoke test for the Cement Quality Intelligence dashboard.
 *
 * Boots the server, loads the dashboard in a real browser, clicks through
 * the raw-mix solver, and fails on any uncaught page error or console error.
 *
 * Requires: node + the `playwright` npm package (system-wide is fine) and a
 * downloaded browser: `npx playwright install chromium`, or set
 * `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to a system Chromium binary. Not part of the
 * pytest suite — run manually: `node tests/smoke_dashboard.mjs`.
 */
import { spawn } from "node:child_process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
let playwright;
try {
  playwright = require("playwright");
} catch {
  console.error("Playwright is not installed. Run: npm install --save-dev playwright");
  process.exit(1);
}

const PORT = 8517;
const BASE = `http://127.0.0.1:${PORT}`;

const server = spawn(
  "./venv/bin/python",
  ["-m", "uvicorn", "app:app", "--port", String(PORT), "--log-level", "warning"],
  { stdio: "ignore", env: { ...process.env, TYPESAFE_API_KEY: "" } },
);

async function waitForApi(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

let browser;
try {
  await waitForApi(`${BASE}/api/data`, 180_000);

  browser = await playwright.chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined,
  });
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" && !m.text().includes("favicon") && !m.location().url.endsWith("/favicon.ico")) {
      errors.push(`console.error: ${m.text()}`);
    }
  });
  await page.route("**/api/rawmix/calculate", async (route) => {
    const response = await route.fetch();
    const json = await response.json();
    json.typesafe = {
      enabled: true,
      action: "adjust_recipe",
      confidence: 0.91,
      probabilities: { monitor: 0.04, adjust_recipe: 0.91, stop_and_review: 0.05 },
      requires_human_review: true,
      review_probability: 0.88,
    };
    await route.fulfill({ response, json });
  });

  await page.goto(BASE, { waitUntil: "load" });
  await page.waitForSelector("#avgStrength", { timeout: 30_000 });
  await page.waitForFunction(
    () => document.getElementById("avgStrength").textContent.includes("MPa") &&
          !document.getElementById("avgStrength").textContent.includes("---"),
    { timeout: 60_000 },
  );

  const avg = await page.textContent("#avgStrength");
  if (!avg) throw new Error("avgStrength panel never populated");

  await page.click("#tabBtnRawMix");
  await page.waitForFunction(
    () => getComputedStyle(document.querySelector(".tab-page") || document.body).display !== "none",
    { timeout: 10_000 },
  ).catch(() => {});
  await page.click("#btnCalculateRawMix");
  await page.waitForFunction(
    () => document.getElementById("raw_result_dry").textContent.includes("Limestone"),
    { timeout: 30_000 },
  );
  const rawMixReview = await page.textContent("#raw_diagnostic_advice");
  if (!rawMixReview.includes("Human-review probability: 88%") || !rawMixReview.includes("Adjust recipe or process targets: 91%")) {
    throw new Error("Detailed TypeSafe raw-mix scores were not rendered");
  }

  // Recipe mode ("Calculate from Recipe") — regression: mode "calc" must
  // not 422 (frontend uses "calc", schema only accepted "recipe")
  await page.click("#raw_mode_calc");
  await page.click("#btnCalculateRawMix");
  await page.waitForFunction(
    () => document.getElementById("raw_result_dry").textContent.includes("Limestone") &&
          document.getElementById("raw_result_wet").textContent.includes("(Y1)"),
    { timeout: 30_000 },
  );

  await page.route("**/api/chat", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      response: "Use the cited operating guidance.",
      sources: [{ file: "kiln-guide.pdf", page: 12, score: 0.63, typesafeScore: 0.97 }],
    }),
  }));
  await page.click("#tabBtnChat");
  await page.fill("#chatInput", "What affects clinker strength?");
  await page.click("#btnSendChat");
  await page.waitForFunction(
    () => document.getElementById("citedSources").textContent.includes("TypeSafe: 97%"),
    { timeout: 10_000 },
  );

  if (errors.length) throw new Error(errors.join("\n"));
  console.log(`SMOKE-OK: page loaded, avgStrength=${avg.trim()}, raw-mix scores + RAG scores rendered`);
} finally {
  if (browser) await browser.close().catch(() => {});
  server.kill();
}
