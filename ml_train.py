"""Train in-memory XGBoost models from the latest CSV (no disk persistence)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import xgboost as xgb
from sklearn.metrics import r2_score

try:
    from sklearn.metrics import root_mean_squared_error as _rmse_fn
except ImportError:  # sklearn < 1.4
    from sklearn.metrics import mean_squared_error as _mse_fn
    def _rmse_fn(y_true, y_pred):
        return float(_mse_fn(y_true, y_pred) ** 0.5)

from sklearn.model_selection import GridSearchCV, KFold

from data_prep import CEMENT_TYPES, ML_EXCLUDED_YEARS, ml_training_frame

ML_FEATURES = [
    "SiO2", "Al2O3", "Fe2O3", "CaO", "MgO", "SO3",
    "Strength_Early", "Early_Strength_Days", "Fineness",
    "Strength_7D", "Residue_80",
]

MIN_TRAIN_SAMPLES = 100
PREDICTIVE_R2 = 0.50
EXPLORATORY_R2 = 0.25


def model_confidence(r2: float) -> str:
    if r2 >= PREDICTIVE_R2:
        return "predictive"
    if r2 >= EXPLORATORY_R2:
        return "exploratory"
    return "chemistry_only"


def train_all_models(df: pd.DataFrame) -> tuple[dict[str, xgb.XGBRegressor], dict[str, Any]]:
    """Retrain every cement-type model from the current dataframe."""
    models: dict[str, xgb.XGBRegressor] = {}
    ml_data: dict[str, Any] = {}

    for c_type in CEMENT_TYPES:
        print(f"Training XGBoost Regressor for {c_type} 28-day strength...")
        df_sub = ml_training_frame(df, c_type)
        df_ml = df_sub[ML_FEATURES + ["Strength_28D", "Date_str"]].dropna()

        r2, rmse = 0.0, 0.0
        feature_importances: dict[str, float] = {}
        feature_averages = (
            {feat: float(df_ml[feat].mean()) for feat in ML_FEATURES}
            if not df_ml.empty
            else {feat: 0.0 for feat in ML_FEATURES}
        )

        date_min = date_max = None
        if not df_ml.empty and "Date_str" in df_ml.columns:
            valid_dates = df_ml["Date_str"].dropna()
            if not valid_dates.empty:
                date_min = str(valid_dates.min())
                date_max = str(valid_dates.max())

        if len(df_ml) >= MIN_TRAIN_SAMPLES:
            # Chronological split: train on the earliest 80% of records,
            # validate on the most recent 20%. The model predicts the future,
            # so validation must never leak future rows into training.
            df_ml = df_ml.sort_values("Date_str").reset_index(drop=True)
            split_idx = int(len(df_ml) * 0.8)
            X = df_ml[ML_FEATURES]
            y = df_ml["Strength_28D"]
            X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
            y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

            val_date_min = str(df_ml["Date_str"].iloc[split_idx])
            val_date_max = str(df_ml["Date_str"].iloc[-1])

            # K-Fold Cross Validation within the training set for hyperparameter tuning
            kf = KFold(n_splits=3, shuffle=True, random_state=42)
            
            param_grid = {
                "n_estimators": [100, 150, 200],
                "learning_rate": [0.05, 0.1],
                "max_depth": [3, 4, 5],
                "subsample": [0.8],
                "colsample_bytree": [0.8],
            }
            
            base_model = xgb.XGBRegressor(random_state=42)
            grid_search = GridSearchCV(
                estimator=base_model,
                param_grid=param_grid,
                cv=kf,
                scoring="neg_root_mean_squared_error",
                n_jobs=-1,
            )
            grid_search.fit(X_train, y_train)
            
            model = grid_search.best_estimator_

            y_pred = model.predict(X_test)
            r2 = float(r2_score(y_test, y_pred))
            rmse = float(_rmse_fn(y_test, y_pred))

            models[c_type] = model
            feature_importances = {
                feat: float(imp) for feat, imp in zip(ML_FEATURES, model.feature_importances_)
            }
            print(f"[{c_type}] Model trained! R2: {r2:.3f}, RMSE: {rmse:.2f} MPa, samples: {len(df_ml)}")
            print(f"[{c_type}] Best params: {grid_search.best_params_}")
        else:
            print(f"[{c_type}] Not enough 28-day records to train ({len(df_ml)} rows).")

        confidence = model_confidence(r2)
        ml_data[c_type] = {
            "r2": round(r2, 3),
            "rmse": round(rmse, 2),
            "importances": feature_importances,
            "averages": feature_averages,
            "trainSamples": int(len(df_ml)),
            "excludedYears": sorted(ML_EXCLUDED_YEARS),
            "strengthDateRange": {"min": date_min, "max": date_max},
            "validationDateRange": {"min": val_date_min, "max": val_date_max},
            "confidence": confidence,
            "confidenceLabel": {
                "predictive": "Predictive model",
                "exploratory": "Exploratory simulation",
                "chemistry_only": "Chemistry guidance only — ML confidence low",
            }[confidence],
            "hasModel": c_type in models,
        }

    return models, ml_data
