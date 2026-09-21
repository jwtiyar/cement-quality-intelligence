"""Leakage-free rolling evaluation for the strength models."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from data_prep import ml_training_frame
from ml_train import ML_FEATURES


def _metrics(y_true: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(y_true, prediction)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, prediction))),
        "r2": float(r2_score(y_true, prediction)),
    }


def _bootstrap_ci(y_true: np.ndarray, prediction: np.ndarray, seed: int = 42, samples: int = 300) -> dict[str, list[float]]:
    rng = np.random.default_rng(seed)
    values = {metric: [] for metric in ("mae", "rmse", "r2")}
    for _ in range(samples):
        indices = rng.integers(0, len(y_true), len(y_true))
        score = _metrics(y_true[indices], prediction[indices])
        for metric in values:
            values[metric].append(score[metric])
    return {metric: [float(np.percentile(scores, 2.5)), float(np.percentile(scores, 97.5))] for metric, scores in values.items()}


def _make_xgb() -> xgb.XGBRegressor:
    return xgb.XGBRegressor(
        n_estimators=150,
        learning_rate=0.05,
        max_depth=3,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=1,
    )


def _model_predictions(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, np.ndarray]:
    X_train, y_train = train[ML_FEATURES], train["Strength_28D"]
    X_test = test[ML_FEATURES]
    xgb_model = _make_xgb()
    ridge = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    xgb_model.fit(X_train, y_train)
    ridge.fit(X_train, y_train)

    recent_cutoff = pd.to_datetime(train["Date_str"].max()) - pd.DateOffset(months=24)
    recent_train = train[pd.to_datetime(train["Date_str"]) >= recent_cutoff]
    recent_xgb = _make_xgb()
    recent_xgb.fit(recent_train[ML_FEATURES], recent_train["Strength_28D"])

    age_days = (pd.to_datetime(train["Date_str"].max()) - pd.to_datetime(train["Date_str"])).dt.days
    weighted_xgb = _make_xgb()
    weighted_xgb.fit(X_train, y_train, sample_weight=np.exp(-age_days.to_numpy() / 365.0))
    return {
        "train_mean": np.full(len(X_test), float(y_train.mean())),
        "recent_mean": np.full(len(X_test), float(y_train.tail(min(100, len(y_train))).mean())),
        "ridge": ridge.predict(X_test),
        "xgboost": xgb_model.predict(X_test),
        "xgboost_recent_24m": recent_xgb.predict(X_test),
        "xgboost_recency_weighted": weighted_xgb.predict(X_test),
    }


def rolling_evaluation(
    df: pd.DataFrame,
    cement_type: str,
    folds: int = 4,
    test_size: int | None = None,
    bootstrap_samples: int = 300,
) -> dict[str, Any]:
    req_cols = ML_FEATURES + ["Strength_28D", "Date_str", "Strength_28D_Source"]
    if "Availability_Date_28D" in df.columns:
        req_cols.append("Availability_Date_28D")

    frame = ml_training_frame(df, cement_type)
    for col in req_cols:
        if col not in frame.columns and col == "Strength_28D_Source":
            frame = frame.copy()
            frame["Strength_28D_Source"] = "unknown"

    avail_cols = [c for c in req_cols if c in frame.columns]
    frame = frame[avail_cols].dropna().sort_values("Date_str").reset_index(drop=True)

    if len(frame) < 60:
        return {
            "cementType": cement_type,
            "status": "insufficient_evidence",
            "reason": f"Not enough rows for rolling evaluation: {cement_type} ({len(frame)} rows; minimum 60 required)",
            "rows": int(len(frame)),
            "folds": [],
            "models": {},
            "promotionDecision": {
                "promoted": False,
                "reason": "Insufficient data to support meaningful time-series validation",
            },
        }

    test_size = test_size or max(20, len(frame) // (folds + 2))
    first_test = len(frame) - (folds * test_size)
    if first_test < 20:
        return {
            "cementType": cement_type,
            "status": "insufficient_evidence",
            "reason": f"Insufficient historical records for {folds} folds with test_size={test_size} ({len(frame)} total rows)",
            "rows": int(len(frame)),
            "folds": [],
            "models": {},
            "promotionDecision": {
                "promoted": False,
                "reason": "Insufficient historical training depth for requested folds",
            },
        }

    predictions: dict[str, list[np.ndarray]] = {
        name: [] for name in ("train_mean", "recent_mean", "ridge", "xgboost", "xgboost_recent_24m", "xgboost_recency_weighted")
    }
    actual: list[np.ndarray] = []
    fold_reports = []
    folds_won = 0

    for fold in range(folds):
        train_end = first_test + fold * test_size
        test_end = train_end + test_size
        train_raw, test = frame.iloc[:train_end], frame.iloc[train_end:test_end]

        test_start_date = pd.to_datetime(test["Date_str"].iloc[0])
        pred_time = test_start_date + pd.Timedelta(days=2)

        if "Availability_Date_28D" in train_raw.columns:
            avail_mask = pd.to_datetime(train_raw["Availability_Date_28D"]) <= pred_time
        else:
            avail_mask = pd.to_datetime(train_raw["Date_str"]) + pd.Timedelta(days=28) <= pred_time

        train = train_raw[avail_mask]
        if len(train) < 10:
            continue

        fold_predictions = _model_predictions(train, test)
        actual.append(test["Strength_28D"].to_numpy())
        for name, prediction in fold_predictions.items():
            predictions[name].append(prediction)

        fold_mae_xgb = float(mean_absolute_error(test["Strength_28D"], fold_predictions["xgboost"]))
        fold_mae_base = float(mean_absolute_error(test["Strength_28D"], fold_predictions["recent_mean"]))
        won = fold_mae_xgb < fold_mae_base
        if won:
            folds_won += 1

        fold_reports.append({
            "fold": fold + 1,
            "trainEnd": str(train["Date_str"].iloc[-1]),
            "testStart": str(test["Date_str"].iloc[0]),
            "testEnd": str(test["Date_str"].iloc[-1]),
            "trainSamplesAvailable": int(len(train)),
            "xgbMae": round(fold_mae_xgb, 3),
            "baselineMae": round(fold_mae_base, 3),
            "xgbBeatBaseline": won,
            "sourceCounts": {str(source): int(count) for source, count in test["Strength_28D_Source"].value_counts().items()} if "Strength_28D_Source" in test.columns else {},
        })

    if not actual:
        return {
            "cementType": cement_type,
            "status": "insufficient_evidence",
            "reason": f"Zero valid evaluation folds after calendar availability purging: {cement_type}",
            "rows": int(len(frame)),
            "folds": [],
            "models": {},
            "promotionDecision": {
                "promoted": False,
                "reason": "Zero valid folds after calendar cutoff",
            },
        }

    y_true = np.concatenate(actual)
    total_eval_folds = len(fold_reports)
    fold_win_ratio = (folds_won / total_eval_folds) if total_eval_folds > 0 else 0.0

    report = {
        "cementType": cement_type,
        "status": "evaluated",
        "rows": int(len(frame)),
        "folds": fold_reports,
        "sourceCounts": {str(source): int(count) for source, count in frame["Strength_28D_Source"].value_counts().items()} if "Strength_28D_Source" in frame.columns else {},
        "models": {},
    }

    for name, chunks in predictions.items():
        if chunks:
            prediction = np.concatenate(chunks)
            report["models"][name] = {
                **_metrics(y_true, prediction),
                "bootstrap95": _bootstrap_ci(y_true, prediction, samples=bootstrap_samples),
            }

    xgb_metrics = report["models"].get("xgboost", {})
    base_metrics = report["models"].get("recent_mean", {})
    xgb_mae = xgb_metrics.get("mae", float("inf"))
    base_mae = base_metrics.get("mae", float("inf"))
    xgb_r2 = xgb_metrics.get("r2", -999.0)

    mae_improvement_pct = ((base_mae - xgb_mae) / base_mae) if (base_mae > 0 and base_mae < float("inf")) else 0.0
    promoted = (
        (total_eval_folds >= 3)
        and (fold_win_ratio >= 0.75)
        and (mae_improvement_pct >= 0.05)
        and (xgb_r2 > 0.25)
    )

    report["promotionDecision"] = {
        "promoted": bool(promoted),
        "totalFolds": total_eval_folds,
        "foldsWon": folds_won,
        "foldsWonRatio": round(fold_win_ratio, 3),
        "maeImprovementPct": round(mae_improvement_pct * 100, 2),
        "overallXgbMae": round(xgb_mae, 3),
        "overallRecentMeanMae": round(base_mae, 3),
        "overallR2": round(xgb_r2, 3),
        "criteria": ">=3 folds, >=75% folds won, >=5% overall MAE improvement, R2 > 0.25",
    }
    return report
