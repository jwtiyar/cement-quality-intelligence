#!/usr/bin/env node
/**
 * Browser smoke test for the Cement Quality Intelligence dashboard.
 *
 * Boots the server, loads the dashboard in a real browser, clicks through
 * the raw-mix solver, and fails on any uncaught page error or console error.
 *
 * Requires: node + the `playwright` npm package (system-wide is fine) and a
 * downloaded browser: `npx playwright install firefox`. Not part of the
 * pytest suite — run manually: `node tests/smoke_dashboard.mjs`.
 */
import { spawn } from "node:child_process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
let playwright;
try {
  playwright = require("playwright");
} catch {
  playwright = require("/home/jwty/node_modules/playwright");
}

const PORT = 8517;
const BASE = `http://127.0.0.1:${PORT}`;

const server = spawn(
  "./venv/bin/python",
  ["-m", "uvicorn", "app:app", "--port", String(PORT), "--log-level", "warning"],
  { stdio: "ignore" },
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

  browser = await playwright.firefox.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" && !m.text().includes("favicon")) {
      errors.push(`console.error: ${m.text()}`);
    }
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

  if (errors.length) throw new Error(errors.join("\n"));
  console.log(`SMOKE-OK: page loaded, avgStrength=${avg.trim()}, raw-mix solved`);
} finally {
  if (browser) await browser.close().catch(() => {});
  server.kill();
}
