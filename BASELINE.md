# Baseline (public)

This document records software-level behavior only. Plant datasets, production
dates, model metrics, and raw laboratory results are intentionally omitted.
The local `ALL_CEMENT_DATA.csv` file is ignored and must be supplied separately
for offline operation.

## Test suite

Run the test suite with:

```bash
./venv/bin/python -m pytest tests/ -v
```

The tests cover chemistry calculations, raw-mix solving, request validation,
dataset normalization, and ML training behavior using local data.

## ML behavior

Models are trained in memory from the local dataset. Exact training counts and
performance metrics depend on the plant dataset and are not published here.

## Raw-mix solver behavior

The solver supports target-modulus and recipe-analysis modes, validates inputs,
calculates clinker chemistry and Bogue phases, and reports feasibility and
sintering diagnostics.
