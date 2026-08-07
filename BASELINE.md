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

## Raw-mix solver (current behavior)

- Feasible OPC targets LSF 95 / SM 2.4 / AM 1.5 →
  Limestone 80.71 · Clay 17.32 · Sand 1.07 · Slag 0.91;
  clinker LSF 95.0, C3S 61.1%, liquid 25.5%.
- Impossible AM target (0.1) → negative proportions returned
  (Clay −4.42), flagged as error after the fact (no constraint solving).
