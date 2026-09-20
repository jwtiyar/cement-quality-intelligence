#!/usr/bin/env python3
"""Print rolling, source-aware strength-model evaluation as JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_prep import load_and_prepare
from ml_evaluation import rolling_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--bootstrap-samples", type=int, default=300)
    args = parser.parse_args()
    data = load_and_prepare()
    report = {
        cement_type: rolling_evaluation(
            data,
            cement_type,
            folds=args.folds,
            bootstrap_samples=args.bootstrap_samples,
        )
        for cement_type in ("OPC", "SRC", "SBC")
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
