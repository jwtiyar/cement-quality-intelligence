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
    frame = ml_training_frame(df, cement_type)[ML_FEATURES + ["Strength_28D", "Date_str", "Strength_28D_Source"]].dropna()
    frame = frame.sort_values("Date_str").reset_index(drop=True)
    if len(frame) < 300:
        raise ValueError(f"Not enough rows for rolling evaluation: {cement_type} ({len(frame)})")
    test_size = test_size or max(100, len(frame) // 10)
    first_test = len(frame) - (folds * test_size)
    if first_test < 100:
        raise ValueError(f"Too many folds for {cement_type}: {folds} x {test_size}")

    predictions: dict[str, list[np.ndarray]] = {name: [] for name in ("train_mean", "recent_mean", "ridge", "xgboost", "xgboost_recent_24m", "xgboost_recency_weighted")}
    actual: list[np.ndarray] = []
    fold_reports = []
    for fold in range(folds):
        train_end = first_test + fold * test_size
        test_end = train_end + test_size
        train, test = frame.iloc[:train_end], frame.iloc[train_end:test_end]
        fold_predictions = _model_predictions(train, test)
        actual.append(test["Strength_28D"].to_numpy())
        for name, prediction in fold_predictions.items():
            predictions[name].append(prediction)
        fold_reports.append({
            "fold": fold + 1,
            "trainEnd": str(train["Date_str"].iloc[-1]),
            "testStart": str(test["Date_str"].iloc[0]),
            "testEnd": str(test["Date_str"].iloc[-1]),
            "sourceCounts": {str(source): int(count) for source, count in test["Strength_28D_Source"].value_counts().items()},
        })

    y_true = np.concatenate(actual)
    report = {
        "cementType": cement_type,
        "rows": int(len(frame)),
        "folds": fold_reports,
        "sourceCounts": {str(source): int(count) for source, count in frame["Strength_28D_Source"].value_counts().items()},
        "models": {},
    }
    for name, chunks in predictions.items():
        prediction = np.concatenate(chunks)
        report["models"][name] = {
            **_metrics(y_true, prediction),
            "bootstrap95": _bootstrap_ci(y_true, prediction, samples=bootstrap_samples),
        }
    return report
