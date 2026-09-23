"""Train in-memory XGBoost models from the latest CSV (no disk persistence)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import xgboost as xgb
import numpy as np
from sklearn.metrics import mean_absolute_error, r2_score

try:
    from sklearn.metrics import root_mean_squared_error as _rmse_fn
except ImportError:  # sklearn < 1.4
    from sklearn.metrics import mean_squared_error as _mse_fn
    def _rmse_fn(y_true, y_pred):
        return float(_mse_fn(y_true, y_pred) ** 0.5)

from data_prep import CEMENT_TYPES, ML_EXCLUDED_YEARS, ml_training_frame

ML_FEATURES = [
    "SiO2", "Al2O3", "Fe2O3", "CaO", "MgO", "SO3",
    "Strength_Early", "Fineness",
]

MIN_TRAIN_SAMPLES = 100
PREDICTIVE_R2 = 0.50
EXPLORATORY_R2 = 0.25


def select_model_training_window(frame: pd.DataFrame) -> pd.DataFrame:
    """Use the latest year when it has enough completed 28-day results."""
    latest_date = pd.to_datetime(frame["Date_str"]).max()
    recent = frame[pd.to_datetime(frame["Date_str"]) >= latest_date - pd.DateOffset(months=12)]
    return recent if len(recent) >= MIN_TRAIN_SAMPLES else frame

def model_confidence(r2: float) -> str:
    if r2 >= PREDICTIVE_R2:
        return "predictive"
    if r2 >= EXPLORATORY_R2:
        return "exploratory"
    return "chemistry_only"


def train_all_models(df: pd.DataFrame) -> tuple[dict[str, xgb.XGBRegressor], dict[str, Any]]:
    """Retrain every cement-type model from the current dataframe."""
    from ml_evaluation import rolling_evaluation

    models: dict[str, xgb.XGBRegressor] = {}
    ml_data: dict[str, Any] = {}

    for c_type in CEMENT_TYPES:
        print(f"Training XGBoost Regressor for {c_type} 28-day strength...")
        df_sub = ml_training_frame(df, c_type)
        if "Strength_28D_Source" not in df_sub.columns:
            # Keep small synthetic callers and older prepared frames compatible.
            df_sub = df_sub.copy()
            df_sub["Strength_28D_Source"] = "unknown"

        cols_to_keep = ML_FEATURES + ["Strength_28D", "Date_str", "Strength_28D_Source"]
        if "Availability_Date_28D" in df_sub.columns:
            cols_to_keep.append("Availability_Date_28D")
        df_ml = df_sub[cols_to_keep].dropna()

        r2, rmse = 0.0, 0.0
        validation_mae = None
        baseline_mae = None
        model_beats_baseline = False
        eval_report: dict[str, Any] = {}
        promo_decision: dict[str, Any] = {"promoted": False, "reason": "Insufficient samples"}
        feature_importances: dict[str, float] = {}
        feature_averages = (
            {feat: float(df_ml[feat].mean()) for feat in ML_FEATURES}
            if not df_ml.empty
            else {feat: 0.0 for feat in ML_FEATURES}
        )

        date_min = date_max = val_date_min = val_date_max = None
        recent_average = None
        model_train_samples = 0
        model_date_min = model_date_max = None
        if not df_ml.empty and "Date_str" in df_ml.columns:
            df_ml = df_ml.sort_values("Date_str").reset_index(drop=True)
            valid_dates = df_ml["Date_str"].dropna()
            if not valid_dates.empty:
                date_min = str(valid_dates.min())
                date_max = str(valid_dates.max())
                recent_average = float(df_ml["Strength_28D"].tail(min(100, len(df_ml))).mean())

        if len(df_ml) >= MIN_TRAIN_SAMPLES:
            # Multi-fold out-of-time rolling evaluation establishes promotion decision
            eval_report = rolling_evaluation(df, c_type, folds=3, bootstrap_samples=50)
            promo_decision = eval_report.get("promotionDecision", {})
            model_beats_baseline = bool(promo_decision.get("promoted", False))

            # Chronological split with calendar-aware 28-day curing delay:
            # Predictions for validation samples are made when the sample is 2 days old.
            # Training samples must have their 28-day strength test physically available
            # at or before that prediction date (sample date + 28 days <= validation sample date + 2 days).
            split_idx = int(len(df_ml) * 0.8)
            val_df = df_ml.iloc[split_idx:].copy()
            val_start_date = pd.to_datetime(val_df["Date_str"].iloc[0])
            pred_time = val_start_date + pd.Timedelta(days=2)

            if "Availability_Date_28D" in df_ml.columns:
                train_mask = pd.to_datetime(df_ml.iloc[:split_idx]["Availability_Date_28D"]) <= pred_time
            else:
                train_mask = pd.to_datetime(df_ml.iloc[:split_idx]["Date_str"]) + pd.Timedelta(days=28) <= pred_time

            train_df = df_ml.iloc[:split_idx][train_mask].copy()

            val_date_min = str(val_df["Date_str"].iloc[0])
            val_date_max = str(val_df["Date_str"].iloc[-1])

            if len(train_df) >= 20:
                policy_train = select_model_training_window(train_df)
                X_train, y_train = policy_train[ML_FEATURES], policy_train["Strength_28D"]
                X_test, y_test = val_df[ML_FEATURES], val_df["Strength_28D"]

                model = xgb.XGBRegressor(
                    n_estimators=150,
                    learning_rate=0.05,
                    max_depth=3,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    random_state=42,
                    n_jobs=1,
                )
                model.fit(X_train, y_train)

                y_pred = model.predict(X_test)
                r2 = float(r2_score(y_test, y_pred))
                rmse = float(_rmse_fn(y_test, y_pred))
                validation_mae = float(mean_absolute_error(y_test, y_pred))

                # The recent-mean baseline uses all calendar-available labels.
                recent_baseline = float(train_df["Strength_28D"].tail(min(100, len(train_df))).mean())
                y_base = np.full(len(y_test), recent_baseline)
                baseline_mae = float(mean_absolute_error(y_test, y_base))
                baseline_rmse = float(_rmse_fn(y_test, y_base))

                final_train = select_model_training_window(df_ml)
                model.fit(final_train[ML_FEATURES], final_train["Strength_28D"])
                models[c_type] = model
                model_train_samples = len(final_train)
                model_date_min = str(final_train["Date_str"].iloc[0])
                model_date_max = str(final_train["Date_str"].iloc[-1])
                feature_averages = {feat: float(final_train[feat].mean()) for feat in ML_FEATURES}
                feature_importances = {
                    feat: float(imp) for feat, imp in zip(ML_FEATURES, model.feature_importances_)
                }
                print(f"[{c_type}] Model trained. ML MAE: {validation_mae:.3f}, Base MAE: {baseline_mae:.3f}, Promoted: {model_beats_baseline}")
            else:
                print(f"[{c_type}] Insufficient training samples after calendar cutoff ({len(train_df)} rows).")
        else:
            print(f"[{c_type}] Not enough 28-day records to train ({len(df_ml)} rows).")

        evaluated_models = eval_report.get("models", {})
        rolling_baseline = evaluated_models.get("recent_mean")
        rolling_model = evaluated_models.get("xgboost")
        if baseline_mae is None or rolling_baseline is None:
            confidence = "insufficient_evidence"
            reported_r2 = None
            reported_rmse = None
        elif model_beats_baseline:
            confidence = model_confidence(rolling_model["r2"])
            reported_r2 = round(rolling_model["r2"], 3)
            reported_rmse = round(rolling_model["rmse"], 2)
        else:
            confidence = "chemistry_only"
            reported_r2 = round(rolling_baseline["r2"], 3)
            reported_rmse = round(rolling_baseline["rmse"], 2)

        ml_data[c_type] = {
            "r2": reported_r2,
            "rmse": reported_rmse,
            "validationMae": round(validation_mae, 3) if validation_mae is not None else None,
            "recentBaselineMae": round(baseline_mae, 3) if baseline_mae is not None else None,
            "recentBaselineRmse": round(baseline_rmse, 2) if baseline_mae is not None else None,
            "modelR2": round(r2, 3) if c_type in models else None,
            "modelRmse": round(rmse, 2) if c_type in models else None,
            "modelBeatsRecentBaseline": model_beats_baseline,
            "promotionDecision": promo_decision,
            "importances": feature_importances,
            "averages": feature_averages,
            "recentAverage": round(recent_average, 3) if recent_average is not None else None,
            "trainSamples": int(len(df_ml)),
            "modelTrainSamples": model_train_samples,
            "modelDateRange": {"min": model_date_min, "max": model_date_max},
            "targetSourceCounts": {
                str(source): int(count)
                for source, count in df_ml["Strength_28D_Source"].value_counts().items()
            },
            "excludedYears": sorted(ML_EXCLUDED_YEARS),
            "strengthDateRange": {"min": date_min, "max": date_max},
            "validationDateRange": {"min": val_date_min, "max": val_date_max},
            "confidence": confidence,
            "confidenceLabel": {
                "predictive": "Predictive model",
                "exploratory": "Exploratory simulation",
                "chemistry_only": "Chemistry guidance only — ML confidence low",
                "insufficient_evidence": "Insufficient evidence for reliable validation",
            }[confidence],
            "hasModel": c_type in models,
        }

    return models, ml_data
