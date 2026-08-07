# Baseline (pre-implementation)

Captured 2026-08-08 before the hardening implementation plan. Commands:
`pytest tests/ -q`, `train_all_models()`, `calculate_rawmix()` (see commit).

## Test suite

- 59 tests, all passing, ~6s.

## Dataset (`ALL_CEMENT_DATA.csv`, via `load_and_prepare()`)

- 11,304 records, years 2013–2026.
- Records by type: OPC 3,866 · SRC 3,842 · SBC 3,596.
- Rows with 28-day strength: 5,909.
- LSF stored as ratio: min 0.914, max 1.003, median 0.972
  (chemistry API / raw-mix solver report LSF as % — units differ by path).

## ML metrics (random 80/20 split, GridSearchCV, seed 42)

| Type | R²   | RMSE (MPa) | Train rows | Confidence |
|------|------|-----------|-----------|------------|
| OPC  | 0.318 | 1.05      | 1,773     | exploratory |
| SRC  | 0.319 | 1.00      | 1,776     | exploratory |
| SBC  | 0.810 | 0.97      | 1,549     | predictive  |

### After Phase 6 (chronological 80/20 split — honest forward metrics)

The random split leaked day-to-day strength autocorrelation into training
(neighbor dates in both splits), inflating R². With the chronological split
(train = earliest 80%, validate = most recent 20%) the forward metrics are:

| Type | R²   | RMSE (MPa) | Train rows | Validation span           | Confidence   |
|------|------|-----------|-----------|---------------------------|--------------|
| OPC  | −3.45 | 1.09     | 1,773     | 2025-02-15 → 2026-05-18   | chemistry_only |
| SRC  | −1.19 | 0.74     | 1,776     | 2025-02-23 → 2026-05-18   | chemistry_only |
| SBC  | −14.81| 1.19     | 1,549     | 2025-04-08 → 2026-05-18   | chemistry_only |

Strength means are near-stationary (2020: 47.5 → 2026: 46.0 OPC), so the
drops reflect true predictive difficulty: future-month strength cannot be
predicted from chemistry at the current sample density (~25 records/month),
and the dashboard now labels all models honestly as "chemistry_only".

## Raw-mix solver (current behavior)

- Feasible OPC targets LSF 95 / SM 2.4 / AM 1.5 →
  Limestone 80.71 · Clay 17.32 · Sand 1.07 · Slag 0.91;
  clinker LSF 95.0, C3S 61.1%, liquid 25.5%.
- Impossible AM target (0.1) → negative proportions returned
  (Clay −4.42), flagged as error after the fact (no constraint solving).
