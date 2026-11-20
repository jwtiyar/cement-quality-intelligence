# Short Design: Smart Lab Quality Warnings & Recent-Window Validation (Approach A)

- **Date:** 2026-11-21
- **Size:** Small change (`state.py`, `ml_train.py`, `ml_evaluation.py`, `dashboard/index.html`, `dashboard/script.js`, tests)

## 1. Intent & Why
Plant laboratory Excel sheets from 2020–2026 contain specific test anomalies (such as SBC-level Blaine values `3700–4109 cm²/g` entered on OPC rows in March–April 2026 while sieve residue `%R,80` was coarse and 2D/28D strengths were low, and 2025 flat `1.0 MPa` 28-day bands). Rather than silently deleting or excluding rows from the dataset, the dashboard should warn engineers clearly about suspect rows and training-window distortions so they can verify and fix the source Excel sheets. At the same time, model validation (`XGBoost R²` and `RMSE`) should evaluate on the recent 24-month operating era (matching the recent-data training philosophy) rather than scoring across the old 2022–2023 regime step drop.

## 2. Goals, Non-Goals & Anti-Goals
- **Goals:**
  1. Detect cement-type-specific out-of-range values (`OPC`, `SRC`, `SBC` have distinct Blaine, `%R,80`, 2D, and 28D ranges).
  2. Detect same-day cross-test physical contradictions (e.g., high OPC/SRC Blaine `> 3600 cm²/g` paired with coarse `%R,80 >= 1.0%` and low strength `< 45.6 MPa`, or `Strength_Early >= Strength_28D`).
  3. Surface a **Training Window Quality Warning** directly inside the **28-Day Compressive Strength Estimator** tab whenever the active 12-month training window has a negative Blaine-vs-28D correlation (`r < -0.15`) or near-zero 2D-vs-28D correlation (`|r| < 0.10`), naming the affected months/dates.
  4. Evaluate `rolling_evaluation` in `ml_train.py` on the new-data window (`Year >= 2025` whenever it has `>= 180` eligible rows for that cement type, falling back to full history for smaller synthetic test fixtures) so displayed `XGBoost RMSE` (`~0.45–0.64 MPa`) and `R²` reflect 2025–2026 plant performance rather than the 2022–2023 step drop.
- **Non-Goals:** Adding a 5th dashboard tab or modifying historical Excel files automatically.
- **Anti-Goals:** Never silently drop, filter out, or alter laboratory rows in `data_prep.py` or `ml_train.py`.

## 3. Approaches Considered
- **Approach A (Selected — Smart Lab Warning Banner + Predictor Health Alert + Recent-Window Validation):** Upgrades `#anomaly_banner` with cement-specific bounds and cross-test contradiction rules, adds a training-window physics warning box on the Strength Estimator card, and runs rolling validation on the recent 24-month era.
- **Approach B (Warnings Only, Keep 2020–2026 Validation):** Leaves `rolling_evaluation` across 2020–2026, which keeps displaying `SBC R²: -1325.6%` from the 2022–2023 step drop. Rejected because validation should match the recent-data training philosophy.
- **Approach C (Dedicated 5th Lab QA Tab):** Adds a full new navigation tab. Rejected as heavier than needed when top-level and predictor-level warnings surface the issues immediately.

## 4. Concrete Design
1. **Cement-Specific Bounds & Cross-Test Contradictions (`cement_app/state.py`):**
   - Keep `ANOMALY_BOUNDS` for global oxide bounds (`SiO2`, `Al2O3`, `Fe2O3`, `CaO`, `MgO`, `SO3`), and add `CEMENT_ANOMALY_BOUNDS`:
     - `OPC`: `Fineness (3000, 3750)`, `Strength_Early (20.0, 29.0)`, `Strength_28D (42.0, 54.0)`, `Residue_80 (0.1, 3.0)`
     - `SRC`: `Fineness (2950, 3750)`, `Strength_Early (20.0, 28.5)`, `Strength_28D (42.0, 54.0)`, `Residue_80 (0.1, 2.8)`
     - `SBC`: `Fineness (3750, 4750)`, `Strength_Early (25.0, 35.0)`, `Strength_28D (48.0, 65.0)`, `Residue_80 (0.05, 1.0)`
   - Add cross-test contradiction checks per row:
     - `OPC` / `SRC`: `Fineness > 3600` AND `Residue_80 >= 1.0` AND (`Strength_28D < 45.6` OR `Strength_Early < 24.5`) $\rightarrow$ `Parameter: "Fineness vs %R,80 & Strength"`, `Expected: "Blaine > 3600 contradicts coarse %R,80 >= 1.0% & low strength"`.
     - Any cement: `Strength_Early >= Strength_28D` $\rightarrow$ `Parameter: "Strength_Early vs Strength_28D"`, `Expected: "2D strength < 28D strength"`.
   - Sort `anomalies` most-recent date first (`Date` descending) so 2025–2026 issues appear at the top of `#anomaly_banner`, and allow expanding to view all items.

2. **Predictor Training-Window Health Alert & New-Data Validation (`cement_app/ml_train.py` & `dashboard/`):**
   - In `ml_train.py`:
     - When `len(df_ml) >= MIN_TRAIN_SAMPLES`, select the new-data slice (`df[df["Year"] >= 2025]`) for `rolling_evaluation` whenever that slice has at least `180` eligible rows for `c_type` (otherwise use `df` so small synthetic test fixtures continue working identically).
     - Compute `trainingWarnings: list[str]` on `final_train` (the 12-month active training window):
       - If `corr(Fineness, Strength_28D) < -0.15`: warn that active training data has an inverse Blaine-vs-28D correlation (`r = ...`) and cite the number of high-Blaine/low-strength rows in that window.
       - If `abs(corr(Strength_Early, Strength_28D)) < 0.10` or `std(Strength_28D) < 0.55`: warn that 28-day strength in the training window has low variation / weak correlation (`r = ...`) with 2-day strength.
   - In `dashboard/index.html` & `dashboard/script.js`:
     - Add `<div id="modelDataWarning" class="advice-card" style="display: none; margin-bottom: 0.75rem; border-color: var(--status-warning); color: var(--status-warning);"></div>` inside the Strength Estimator panel right under `.model-stats` and populate it from `modelData.trainingWarnings`.
     - In `#anomaly_banner` (`script.js`), show the newest anomalies first, fix the button name reference to `"Refresh Data"`, and add a `<details>` toggle when there are more than 5 anomalies so the user can inspect the full list in-place.
