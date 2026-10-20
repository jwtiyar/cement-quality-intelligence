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
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { delimiter, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
let playwright;
try {
  playwright = require("playwright");
} catch {
  const fallbackPaths = [
    "/home/jwty/node_modules/.pnpm/node_modules/playwright",
    "/home/jwty/node_modules/playwright",
  ];
  for (const p of fallbackPaths) {
    try {
      playwright = require(p);
      break;
    } catch {}
  }
  if (!playwright) {
    console.error("Playwright is not installed. Run: npm install --save-dev playwright");
    process.exit(1);
  }
}

const PORT = 8517;
const BASE = `http://127.0.0.1:${PORT}`;

const appDir = fileURLToPath(new URL("../", import.meta.url));
const venvPython = join(appDir, "venv/bin/python");
const pythonBin = process.env.PYTHON_BIN || (existsSync(venvPython) ? venvPython : "python");
const syntheticCsv = fileURLToPath(new URL("./fixtures/synthetic_cement_data.csv", import.meta.url));
const smokeDir = mkdtempSync(join(tmpdir(), "cement-smoke-"));

const server = spawn(
  pythonBin,
  ["-m", "uvicorn", "app:app", "--port", String(PORT), "--log-level", "warning"],
  {
    cwd: smokeDir,
    stdio: "ignore",
    env: {
      ...process.env,
      PYTHONPATH: `${appDir}${process.env.PYTHONPATH ? delimiter + process.env.PYTHONPATH : ""}`,
      CEMENT_DATA_CSV: syntheticCsv,
      TYPESAFE_API_KEY: "",
    },
  },
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
    json.explanation += '<img src="x" onerror="window.__unsafeExplanationRan = true">';
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
  if (await page.title() !== "Cement Quality Intelligence") throw new Error("Dashboard title was not updated");
  await page.selectOption("#themeSelector", "light");
  if (await page.getAttribute("html", "data-theme-resolved") !== "light" || await page.evaluate(() => localStorage.getItem("cementTheme")) !== "light") {
    throw new Error("Light theme was not applied and persisted");
  }
  await page.reload({ waitUntil: "load" });
  if (await page.inputValue("#themeSelector") !== "light" || await page.getAttribute("html", "data-theme-resolved") !== "light") {
    throw new Error("Saved light theme was not restored");
  }
  await page.selectOption("#themeSelector", "dark");
  if (await page.getAttribute("html", "data-theme-resolved") !== "dark") throw new Error("Dark theme was not applied");
  await page.selectOption("#themeSelector", "system");
  if (await page.evaluate(() => localStorage.getItem("cementTheme")) !== "system") throw new Error("System theme was not persisted");
  await page.waitForSelector("#avgStrength", { timeout: 30_000 });
  await page.waitForFunction(
    () => document.getElementById("avgStrength").textContent.includes("MPa") &&
          !document.getElementById("avgStrength").textContent.includes("---"),
    { timeout: 60_000 },
  );

  const avg = await page.textContent("#avgStrength");
  if (!avg) throw new Error("avgStrength panel never populated");

  await page.selectOption("#avgYearSelect", "2024");
  await page.selectOption("#avg3mSelect", "months_12,1,2");
  await page.waitForFunction(() => document.getElementById("activePeriodBadge").textContent.includes("Dec 2024 – Feb 2025"));
  if (await page.textContent("#yearsCoverage") !== "Dec 2024 – Feb 2025") {
    throw new Error("Cross-year coverage was not displayed");
  }
  await page.click('[data-period="season_winter"]');
  await page.waitForFunction(() => document.getElementById("activePeriodBadge").textContent.includes("Winter") &&
    document.getElementById("activePeriodBadge").textContent.includes("Dec 2024 – Feb 2025"));
  await page.click("#btnResetAvgPeriod");
  await page.waitForFunction(() => document.getElementById("activePeriodBadge").textContent === "Full Dataset (All Time)");

  await page.focus("#tabBtnAnalytics");
  await page.keyboard.press("ArrowRight");
  if (new URL(page.url()).hash !== "#ai" || await page.getAttribute("#tabBtnAI", "aria-selected") !== "true") {
    throw new Error("Keyboard tab navigation did not update URL and selected state");
  }

  await page.click("#tabBtnAI");
  if (new URL(page.url()).hash !== "#ai" || await page.getAttribute("#tabBtnAI", "aria-selected") !== "true") {
    throw new Error("Strength estimate tab did not update URL and selected state");
  }
  if (!await page.textContent("#opt_res_strength").then((text) => text.includes("MPa"))) {
    throw new Error("Recent average was not shown before entering test values");
  }
  for (const [id, value] of Object.entries({
    opt_CaO: "65", opt_SiO2: "21.5", opt_Al2O3: "5.5", opt_Fe2O3: "3.5",
    opt_MgO: "1.5", opt_SO3: "0.8", opt_Strength_Early: "24", opt_Fineness: "3800",
  })) await page.fill(`#${id}`, value);
  await page.waitForFunction(() =>
    document.getElementById("opt_res_strength").textContent.includes("MPa") &&
    document.getElementById("opt_res_model_strength").textContent.includes("MPa"),
    { timeout: 30_000 },
  );

  for (const delayedEndpoint of ["chemistry/analyze", "predict"]) {
    let releaseOld;
    const oldHeld = new Promise(resolve => { releaseOld = resolve; });
    let oldArrived;
    const arrived = new Promise(resolve => { oldArrived = resolve; });
    let oldCompleted;
    const completed = new Promise(resolve => { oldCompleted = resolve; });
    const pattern = `**/api/${delayedEndpoint}`;
    await page.route(pattern, async route => {
      const body = route.request().postDataJSON();
      const response = await route.fetch();
      if (body.CaO === 60) {
        oldArrived();
        await oldHeld;
      }
      await route.fulfill({ response });
      if (body.CaO === 60) oldCompleted();
    });
    await page.fill("#opt_CaO", "60");
    await arrived;
    const newPrediction = page.waitForResponse(response => response.url().endsWith('/api/predict') && response.request().postDataJSON().CaO === 65.5);
    await page.fill("#opt_CaO", "65.5");
    await newPrediction;
    await page.waitForFunction(() => latestPredictionContext !== null);
    const latest = await page.evaluate(() => JSON.stringify({
      context: latestPredictionContext,
      lsf: document.getElementById("opt_res_LSF").textContent,
      model: document.getElementById("opt_res_model_strength").textContent,
    }));
    releaseOld();
    await completed;
    await page.waitForTimeout(300);
    const afterOld = await page.evaluate(() => JSON.stringify({
      context: latestPredictionContext,
      lsf: document.getElementById("opt_res_LSF").textContent,
      model: document.getElementById("opt_res_model_strength").textContent,
    }));
    if (latest !== afterOld) throw new Error(`Stale ${delayedEndpoint} response replaced the latest estimate`);
    await page.unroute(pattern);
  }
  await page.fill("#opt_CaO", "");
  if (await page.evaluate(() => latestPredictionContext !== null)) throw new Error("Incomplete inputs retained assistant prediction context");
  await page.fill("#opt_CaO", "65.5");
  await page.waitForFunction(() => latestPredictionContext !== null);
  const chemistry = await page.request.post(`${BASE}/api/chemistry/analyze`, { data: {
    material_type: "cement", CaO: 65.5, SiO2: 21.5, Al2O3: 5.5, Fe2O3: 3.5, MgO: 1.5, SO3: 0.8,
  } });
  if (await page.textContent("#opt_res_LSF") !== (await chemistry.json()).moduli.LSF.toFixed(2)) {
    throw new Error("Strength screen did not request cement chemistry");
  }
  const errorsBeforeFailure = errors.length;
  await page.route("**/api/predict", route => route.fulfill({ status: 503, body: "Unavailable" }));
  await page.fill("#opt_CaO", "64");
  await page.waitForFunction(() => document.getElementById("opt_res_model_strength").textContent === "Could not calculate");
  if (await page.evaluate(() => latestPredictionContext !== null)) throw new Error("Failed prediction retained assistant context");
  const failureErrors = errors.splice(errorsBeforeFailure);
  errors.push(...failureErrors.filter(error => !error.includes("503") ||
    (!error.includes("Strength prediction failed") && !error.includes("Failed to load resource"))));
  await page.unroute("**/api/predict");
  await page.fill("#opt_CaO", "65.5");
  await page.waitForFunction(() => latestPredictionContext !== null);
  await page.screenshot({ path: process.env.CEMENT_SMOKE_SCREENSHOT || "/tmp/cement-strength-regression.png", fullPage: true });

  await page.click("#tabBtnRawMix");
  if (new URL(page.url()).hash !== "#rawmix" || await page.getAttribute("#tabBtnRawMix", "aria-selected") !== "true") {
    throw new Error("Raw-mix tab did not update URL and selected state");
  }
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
  if (await page.locator("#rawmix_prompt_block img").count() || await page.evaluate(() => window.__unsafeExplanationRan === true)) {
    throw new Error("Unsafe raw-mix explanation HTML was rendered");
  }

  for (const [heat, calorific, badge, costLabel, cost] of [
    [900, 10000, "Above consumption benchmark", "Daily cost increase", "26,879"],
    [650, 9200, "Below consumption benchmark", "Daily savings", "9,012"],
    [740, 9800, "At consumption benchmark", "Daily cost change", "0"],
  ]) {
    await page.fill("#raw_hfo_heat", String(heat));
    await page.fill("#raw_hfo_cal", String(calorific));
    await page.click("#btnCalculateRawMix");
    await page.waitForFunction(expected => document.getElementById("econ_status_badge").textContent === expected, badge);
    const alert = await page.textContent("#econ_calorific_alert_box");
    if (!alert.includes(`${costLabel}: $${cost} / day`)) {
      throw new Error(`Incorrect economic impact for heat=${heat}, calorific=${calorific}: ${alert}`);
    }
  }
  await page.screenshot({ path: "/tmp/cement-economics-regression.png", fullPage: true });

  // Recipe mode ("Calculate from Recipe") — regression: mode "calc" must
  // not 422 (frontend uses "calc", schema only accepted "recipe")
  await page.click("#raw_mode_calc");
  await page.click("#btnCalculateRawMix");
  await page.waitForFunction(
    () => document.getElementById("raw_result_dry").textContent.includes("Limestone") &&
          document.getElementById("raw_result_wet").textContent.includes("(Y1)"),
    { timeout: 30_000 },
  );

  await page.route("**/api/chat", (route) => {
    if (route.request().postDataJSON().provider !== "codex") {
      throw new Error("Selected assistant provider was not sent to the API");
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        response: "Use the cited operating guidance.",
        provider: "codex",
        model: "gpt-5.6-luna (medium)",
        sources: [{ file: "kiln-guide.pdf", page: 12, score: 0.63, typesafeScore: 0.97 }],
      }),
    });
  });
  await page.click("#tabBtnChat");
  await page.selectOption("#aiProvider", "codex");
  await page.fill("#chatInput", "What affects clinker strength?");
  await page.click("#btnSendChat");
  await page.waitForFunction(
    () => document.getElementById("citedSources").textContent.includes("TypeSafe: 97%"),
    { timeout: 10_000 },
  );
  if (!await page.textContent("#activeModelLabel").then((text) => text.includes("Last response: gpt-5.6-luna"))) {
    throw new Error("Assistant did not show the model used for the last response");
  }

  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await mobile.goto(`${BASE}/#analytics`, { waitUntil: "load" });
  await mobile.click("#tabBtnAI");
  if (!await mobile.isVisible("#modelPredictionResult")) throw new Error("Model estimate is not visible on mobile");
  await mobile.screenshot({ path: "/tmp/cement-strength-mobile.png", fullPage: true });
  const overflow = await mobile.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (overflow > 1) throw new Error(`Mobile page overflows horizontally by ${overflow}px`);
  await mobile.click("#tabBtnRawMix");
  if (!await mobile.isVisible("#rawmix_prompt_block")) throw new Error("Raw-mix workspace is not available on mobile");
  await mobile.close();

  if (errors.length) throw new Error(errors.join("\n"));
  console.log(`SMOKE-OK: page loaded, avgStrength=${avg.trim()}, raw-mix scores + RAG scores rendered`);
} finally {
  if (browser) await browser.close().catch(() => {});
  server.kill();
  rmSync(smokeDir, { recursive: true, force: true });
}
