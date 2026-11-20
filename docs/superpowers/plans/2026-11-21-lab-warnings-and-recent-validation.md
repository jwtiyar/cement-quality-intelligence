# Smart Lab Quality Warnings & New-Data Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Warn engineers on the dashboard about cement-specific lab test typos, cross-test physical contradictions, and active training-window correlation distortions (without removing any rows), while evaluating model validation (`XGBoost R²` and `RMSE`) on the new `2025–2026` data era.

**Architecture:** `cement_app/state.py` gains `detect_lab_anomalies(df)` checking global oxide bounds, cement-specific physical bounds (`OPC`, `SRC`, `SBC`), and same-day cross-test contradictions (high Blaine vs. coarse `%R,80` & low strength; `2D >= 28D`), sorted newest-first. `cement_app/ml_train.py` adds `select_validation_frame(df, cement_type)` to run `rolling_evaluation` on `Year >= 2025` (when `>= 180` eligible rows exist, falling back to `df` for small synthetic fixtures) and `detect_training_window_warnings(train_win, cement_type)` to populate `ml_data[c_type]["trainingWarnings"]`. `dashboard/index.html` and `dashboard/script.js` render the expandable top anomaly list and the predictor card's `#modelDataWarning` alert.

**Tech Stack:** Python 3.12+, Pandas, NumPy, XGBoost, FastAPI, Vanilla HTML/CSS/JS, Pytest, Playwright (`smoke_dashboard.mjs`).

**Spec:** `cement_app/docs/superpowers/specs/2026-11-21-lab-warnings-and-recent-validation-design.md`

## Global Constraints

- Never silently drop, filter out, or alter laboratory rows in `data_prep.py`, `ml_train.py`, or `ALL_CEMENT_DATA.csv`.
- Global oxide bounds remain `ANOMALY_BOUNDS = {"SiO2": (17, 26), "Al2O3": (2, 8), "Fe2O3": (1, 6), "CaO": (55, 70), "MgO": (0, 6), "SO3": (0.5, 4.5)}`.
- Cement-specific bounds are `CEMENT_ANOMALY_BOUNDS`:
  - `OPC`: `Fineness: (3000, 3750)`, `Strength_Early: (20.0, 29.0)`, `Strength_28D: (42.0, 54.0)`, `Residue_80: (0.1, 3.0)`
  - `SRC`: `Fineness: (2950, 3750)`, `Strength_Early: (20.0, 28.5)`, `Strength_28D: (42.0, 54.0)`, `Residue_80: (0.1, 2.8)`
  - `SBC`: `Fineness: (3750, 4750)`, `Strength_Early: (25.0, 35.0)`, `Strength_28D: (48.0, 65.0)`, `Residue_80: (0.05, 1.0)`
- Cross-test contradiction rules:
  - `OPC` / `SRC`: `Fineness > 3600` and `Residue_80 >= 1.0` and (`Strength_28D < 45.6` or `Strength_Early < 24.5`).
  - Any cement type: `Strength_Early >= Strength_28D` when both are non-null.
- All user/CSV strings rendered into `#anomaly_banner` or `#modelDataWarning` must be HTML-escaped via `escapeHtml(...)`.
- Run `betterleaks git .` before any commit.

## Review Focus

1. **String `Value` in cross-test contradiction anomalies:** `detect_lab_anomalies` produces human-readable strings for cross-test contradictions (e.g., `"Blaine 4109, %R80 1.0%, 28D 45.1 MPa"`) while single-parameter anomalies produce numeric floats; both `state.py` and `script.js` must handle `int | float | str` values without `TypeError` or `NaN`.
2. **Missing optional columns (`Residue_80`, `Strength_Early`, `Strength_28D`) in synthetic DataFrames:** `detect_lab_anomalies` and `detect_training_window_warnings` must not raise `KeyError` when called on minimal synthetic test frames lacking `Residue_80`.
3. **Small synthetic datasets (`< 180` rows per cement type, e.g. `synthetic_cement_data.csv` with 120 rows/type):** `select_validation_frame` must fall back to the full dataframe when `Year >= 2025` has fewer than `180` complete rows so existing synthetic tests pass unchanged.
4. **Constant or zero-variance series in `detect_training_window_warnings`:** `.corr()` returns `NaN` when a feature or target is constant in a synthetic test; checks must guard with `pd.notna(corr_val)` so `"trainingWarnings"` never contains `"nan"` or crashes.
5. **XSS safety in `#modelDataWarning` and expandable `<details>` in `#anomaly_banner`:** All items in `dashboardData.anomalies` (both top 5 and remaining items inside `<details>`) and `modelData.trainingWarnings` must pass through `escapeHtml`.

---

### Task 1: Cement-Specific Lab Anomaly Bounds & Cross-Test Contradictions (`state.py`)

**Files:**
- Modify: `cement_app/state.py:27-36,322-337`
- Test: `cement_app/tests/test_api.py`

**Interfaces:**
- Produces:
  - `CEMENT_ANOMALY_BOUNDS: dict[str, dict[str, tuple[float, float]]]` in `cement_app/state.py`
  - `detect_lab_anomalies(df: pd.DataFrame) -> list[dict[str, Any]]` in `cement_app/state.py` (each item has keys `"Date"`, `"Type"`, `"Parameter"`, `"Value"`, `"Expected"`, sorted by `"Date"` descending)

- [ ] **Step 1: Write the failing unit tests in `cement_app/tests/test_api.py`**

```python
class TestLabAnomalyDetection:
    def test_detects_cement_specific_blaine_and_cross_test_contradictions(self):
        import pandas as pd
        import state

        df = pd.DataFrame([
            {
                "Date_str": "2026-04-01",
                "Cement_Type": "OPC",
                "SiO2": 19.69, "Al2O3": 5.0, "Fe2O3": 3.5, "CaO": 63.66, "MgO": 2.5, "SO3": 2.4,
                "Fineness": 4109.0,
                "Residue_80": 1.0,
                "Strength_Early": 24.4,
                "Strength_28D": 45.1,
            },
            {
                "Date_str": "2026-04-02",
                "Cement_Type": "SBC",
                "SiO2": 20.0, "Al2O3": 4.8, "Fe2O3": 3.4, "CaO": 62.5, "MgO": 2.2, "SO3": 2.3,
                "Fineness": 4109.0,
                "Residue_80": 0.2,
                "Strength_Early": 30.5,
                "Strength_28D": 53.4,
            },
            {
                "Date_str": "2026-04-03",
                "Cement_Type": "SRC",
                "SiO2": 20.5, "Al2O3": 4.2, "Fe2O3": 4.5, "CaO": 63.0, "MgO": 2.0, "SO3": 2.1,
                "Fineness": 3300.0,
                "Residue_80": 0.8,
                "Strength_Early": 47.0,
                "Strength_28D": 46.0,
            },
        ])
        anomalies = state.detect_lab_anomalies(df)
        opc_params = [a["Parameter"] for a in anomalies if a["Type"] == "OPC"]
        sbc_params = [a["Parameter"] for a in anomalies if a["Type"] == "SBC"]
        src_params = [a["Parameter"] for a in anomalies if a["Type"] == "SRC"]

        assert "Fineness" in opc_params
        assert "Fineness vs %R,80 & Strength" in opc_params
        assert sbc_params == []
        assert "Strength_Early" in src_params
        assert "Strength_Early vs Strength_28D" in src_params
        assert anomalies[0]["Date"] >= anomalies[-1]["Date"]

    def test_detect_lab_anomalies_handles_missing_optional_columns(self):
        import pandas as pd
        import state

        df = pd.DataFrame([
            {"Date_str": "2026-01-01", "Cement_Type": "OPC", "CaO": 63.0, "Fineness": 3350.0}
        ])
        assert state.detect_lab_anomalies(df) == []
```

- [ ] **Step 2: Run pytest to verify the new tests fail**

Run: `cd "/home/jwty/My-projects-Vibe/Cement Data, ML and Rawmix Solver/cement_app" && ./venv/bin/python -m pytest tests/test_api.py -k "TestLabAnomalyDetection" -v`
Expected: FAIL with `AttributeError: module 'state' has no attribute 'detect_lab_anomalies'`

- [ ] **Step 3: Implement `CEMENT_ANOMALY_BOUNDS` and `detect_lab_anomalies(df: pd.DataFrame) -> list[dict[str, Any]]` in `cement_app/state.py`**

Define `ANOMALY_BOUNDS` for the 6 oxides (`SiO2`, `Al2O3`, `Fe2O3`, `CaO`, `MgO`, `SO3`), add `CEMENT_ANOMALY_BOUNDS` with the exact Global Constraints tuples, implement `detect_lab_anomalies(df)` checking oxide bounds, cement-specific bounds, and the two cross-test contradiction rules, sort by `Date` descending, and call `anomalies = detect_lab_anomalies(df)` in `_build_cache_and_snapshot`.

- [ ] **Step 4: Run pytest to verify Task 1 passes**

Run: `cd "/home/jwty/My-projects-Vibe/Cement Data, ML and Rawmix Solver/cement_app" && ./venv/bin/python -m pytest tests/test_api.py -k "TestLabAnomalyDetection" -v`
Expected: PASS (`2 passed`)

---

### Task 2: New-Data Validation (`2025–2026`) & Training-Window Physics Warnings (`ml_train.py`)

**Files:**
- Modify: `cement_app/ml_train.py:30-195`
- Modify: `cement_app/tests/test_ml_train.py:28-95`

**Interfaces:**
- Produces:
  - `NEW_DATA_MIN_YEAR = 2025` and `MIN_RECENT_EVAL_SAMPLES = 180` in `cement_app/ml_train.py`
  - `select_validation_frame(df: pd.DataFrame, cement_type: str, min_rows: int = MIN_RECENT_EVAL_SAMPLES) -> pd.DataFrame` in `cement_app/ml_train.py`
  - `detect_training_window_warnings(train_win: pd.DataFrame, cement_type: str) -> list[str]` in `cement_app/ml_train.py`
  - `ml_data[c_type]["trainingWarnings"]: list[str]` in `train_all_models` output

- [ ] **Step 1: Write failing tests in `cement_app/tests/test_ml_train.py`**

Update `test_displayed_metrics_are_from_the_same_rolling_policy_as_promotion` to use `select_validation_frame(df, "OPC")` and add tests for `select_validation_frame` and `detect_training_window_warnings`:

```python
    def test_displayed_metrics_are_from_the_same_rolling_policy_as_promotion(self):
        from ml_train import select_validation_frame
        df = load_and_prepare()
        _, meta = train_all_models(df)
        eval_df = select_validation_frame(df, "OPC")
        report = rolling_evaluation(eval_df, "OPC", folds=3, bootstrap_samples=2)

        assert meta["OPC"]["r2"] == round(report["models"]["xgboost"]["r2"], 3)
        assert meta["OPC"]["rmse"] == round(report["models"]["xgboost"]["rmse"], 2)
        assert meta["OPC"]["rmse"] < 1.0  # 2025-2026 new-data RMSE (~0.64 MPa)

    def test_training_warnings_detect_negative_blaine_and_handle_constant_series(self):
        from ml_train import detect_training_window_warnings
        dates = pd.date_range("2026-01-01", periods=40, freq="D")
        inv_rows = [
            {
                "Date_str": d.strftime("%Y-%m-%d"),
                "Fineness": 3300.0 + i * 20.0,
                "Strength_Early": 25.0,
                "Strength_28D": 47.0 - i * 0.08,
            }
            for i, d in enumerate(dates)
        ]
        warnings = detect_training_window_warnings(pd.DataFrame(inv_rows), "OPC")
        assert any("Blaine" in w and "negative" in w.lower() for w in warnings)
        assert all("nan" not in w.lower() for w in warnings)
```

- [ ] **Step 2: Run pytest to verify the tests fail**

Run: `cd "/home/jwty/My-projects-Vibe/Cement Data, ML and Rawmix Solver/cement_app" && ./venv/bin/python -m pytest tests/test_ml_train.py -k "displayed_metrics or training_warnings" -v`
Expected: FAIL with `ImportError: cannot import name 'select_validation_frame' from 'ml_train'`

- [ ] **Step 3: Implement `select_validation_frame` and `detect_training_window_warnings` in `cement_app/ml_train.py`**

1. `select_validation_frame(df: pd.DataFrame, cement_type: str, min_rows: int = MIN_RECENT_EVAL_SAMPLES) -> pd.DataFrame`:
   If `"Year"` is in `df.columns`, slice `recent = df[df["Year"] >= NEW_DATA_MIN_YEAR]`. Count rows in `ml_training_frame(recent, cement_type)` that have non-null `ML_FEATURES + ["Strength_28D", "Date_str"]`. Return `recent` if count `>= min_rows`, else `df`.
2. `detect_training_window_warnings(train_win: pd.DataFrame, cement_type: str) -> list[str]`:
   If `len(train_win) < 30`, return `[]`. Check:
   - `r_fin = train_win["Fineness"].corr(train_win["Strength_28D"])` (guarding `train_win["Fineness"].std() > 0` and `train_win["Strength_28D"].std() > 0`): if `pd.notna(r_fin) and r_fin < -0.15`, append a warning message naming `{cement_type}`, `r = {r_fin:.2f}`, and date range `{d_min} → {d_max}`.
   - `r_early = train_win["Strength_Early"].corr(train_win["Strength_28D"])` and `s28_std = float(train_win["Strength_28D"].std())`: if `(pd.notna(r_early) and abs(r_early) < 0.10) or (pd.notna(s28_std) and s28_std < 0.55)`, append a warning message noting low 28D variation (`std = {s28_std:.2f} MPa`) or weak 2D-vs-28D correlation (`r = {r_early:.2f}` when `pd.notna(r_early)` else `"flat"`).
3. In `train_all_models(df)`:
   - Pass `eval_df = select_validation_frame(df, c_type)` into `rolling_evaluation(eval_df, c_type, folds=3, bootstrap_samples=50)`.
   - Compute `training_warnings = detect_training_window_warnings(final_train, c_type)` when a model is fit (else `[]`) and store `"trainingWarnings": training_warnings` in `ml_data[c_type]`.

- [ ] **Step 4: Run pytest on `tests/test_ml_train.py` to verify it passes**

Run: `cd "/home/jwty/My-projects-Vibe/Cement Data, ML and Rawmix Solver/cement_app" && ./venv/bin/python -m pytest tests/test_ml_train.py -v`
Expected: PASS (`13 passed`)

---

### Task 3: Dashboard Warning Display (`index.html`, `script.js`, `smoke_dashboard.mjs`)

**Files:**
- Modify: `cement_app/dashboard/index.html:386-392,937`
- Modify: `cement_app/dashboard/script.js:317-337,1014-1048`
- Modify: `cement_app/tests/smoke_dashboard.mjs:149-166`

**Interfaces:**
- Consumes: `dashboardData.anomalies` (`list[{Date, Type, Parameter, Value, Expected}]`) and `dashboardData.ml[cType].trainingWarnings` (`list[str]`)
- Produces: `#modelDataWarning` DOM container in `index.html`, expandable `<details>` list in `#anomaly_banner` in `script.js`

- [ ] **Step 1: Add `#modelDataWarning` to `cement_app/dashboard/index.html` and bump `script.js?v=21`**

Insert right after `<div class="model-stats">...</div>`:
```html
                    <div id="modelDataWarning" class="advice-card" style="display: none; margin-bottom: 0.75rem; border-color: var(--status-warning); color: var(--status-warning); font-size: 0.8rem;"></div>
```
And update `<script src="script.js?v=20"></script>` to `<script src="script.js?v=21"></script>`.

- [ ] **Step 2: Update `#anomaly_banner` and `updateModelUI` in `cement_app/dashboard/script.js`**

1. In `#anomaly_banner` rendering (`script.js:318-336`):
   - Format each anomaly item with `escapeHtml(String(a.Date))`, `escapeHtml(String(a.Type))`, `escapeHtml(String(a.Parameter))`, `escapeHtml(String(a.Value))`, and `escapeHtml(String(a.Expected))`.
   - Render the first 5 items in `<ul>`, and if `dashboardData.anomalies.length > 5`, render `<details style="margin-top: 0.4rem;"><summary style="cursor: pointer;">Show all ${dashboardData.anomalies.length} warnings (${dashboardData.anomalies.length - 5} more)</summary><ul style="margin: 0.4rem 0 0; padding-left: 1.5rem;">...</ul></details>`.
   - Change `"Sync Live Excel Data"` to `"Refresh Data"`.
2. In `updateModelUI(cType, ...)` (`script.js:1014-1048`):
   - Select `const warnEl = document.getElementById('modelDataWarning');`.
   - If `warnEl` exists and `Array.isArray(modelData.trainingWarnings) && modelData.trainingWarnings.length > 0`, set `warnEl.style.display = 'block'` and `warnEl.innerHTML = '<strong>Lab Training Data Warning:</strong><br>' + modelData.trainingWarnings.map(w => '• ' + escapeHtml(String(w))).join('<br>');`, otherwise set `warnEl.style.display = 'none'` and `warnEl.innerHTML = ''`.

- [ ] **Step 3: Add verification in `cement_app/tests/smoke_dashboard.mjs` and run full verification**

In `smoke_dashboard.mjs` after switching to `#tabBtnAI`, verify `#modelR2` text begins with `"XGBoost R²:"` and `#modelDataWarning` exists in the DOM.

Run:
```bash
cd "/home/jwty/My-projects-Vibe/Cement Data, ML and Rawmix Solver/cement_app" && \
./venv/bin/python -m pytest tests/ -v && \
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium node tests/smoke_dashboard.mjs && \
betterleaks git .
```
Expected: All `pytest` tests PASS, `SMOKE-OK`, and `betterleaks` reports `no leaks found`.
