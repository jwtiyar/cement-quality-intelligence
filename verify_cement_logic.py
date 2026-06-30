import os

import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

try:
    from sklearn.metrics import root_mean_squared_error as _rmse_fn
except ImportError:
    from sklearn.metrics import mean_squared_error as _mse_fn
    def _rmse_fn(y_true, y_pred):
        return float(_mse_fn(y_true, y_pred) ** 0.5)

from chemistry import OxideAnalysis, calc_bogue, calc_moduli
from data_prep import CEMENT_TYPES, load_and_prepare, ml_training_frame
from ml_train import ML_FEATURES, train_all_models


def test_chemical_logic():
    print("\n" + "=" * 80)
    print("TEST 1: CHEMICAL MODULI & BOGUE MATH VERIFICATION (FLSmidth / ASTM C150)")
    print("=" * 80)

    ox = OxideAnalysis(SiO2=19.18, Al2O3=4.96, Fe2O3=3.90, CaO=62.51, SO3=2.26)
    mod = calc_moduli(ox)
    phases = calc_bogue(ox)

    expected = {
        "LSF": 0.9797,
        "SM": 2.1648,
        "AM": 1.2718,
        "C3S": 63.3664,
        "C2S": 7.1854,
        "C3A": 6.5452,
        "C4AF": 11.8677,
    }
    computed = {
        "LSF": mod.LSF,
        "SM": mod.SM,
        "AM": mod.AM,
        "C3S": phases.C3S,
        "C2S": phases.C2S,
        "C3A": phases.C3A,
        "C4AF": phases.C4AF,
    }

    print(f"Input Oxides: CaO={ox.CaO}%, SiO2={ox.SiO2}%, Al2O3={ox.Al2O3}%, Fe2O3={ox.Fe2O3}%, SO3={ox.SO3}%")
    print("-" * 80)
    print(f"{'Modulus/Phase':<13} | {'Computed':<14} | {'Expected':<20} | {'Diff':<10} | Status")
    print("-" * 80)

    for label, comp in computed.items():
        exp = expected[label]
        diff = abs(comp - exp)
        status = "PASSED ✅" if diff < 0.002 else "FAILED ❌"
        print(f"{label:<13} | {comp:<14.4f} | {exp:<20.4f} | {diff:<10.6f} | {status}")

    print("=" * 80)


def test_ml_logic():
    print("\n" + "=" * 80)
    print("TEST 2: AI MACHINE LEARNING MODEL VALIDATION (XGBoost Metrics)")
    print("=" * 80)

    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ALL_CEMENT_DATA.csv")
    if not os.path.exists(csv_path):
        print(f"Error: ALL_CEMENT_DATA.csv not found at {csv_path}.")
        return

    df = load_and_prepare(csv_path)
    models, ml_data = train_all_models(df)
    trained_models = {}

    for ct in CEMENT_TYPES:
        sub_df = ml_training_frame(df, ct)
        sub_df = sub_df.dropna(subset=ML_FEATURES + ["Strength_28D"])
        if sub_df.empty:
            print(f"No records found for type {ct} to validate.")
            continue

        if ct not in models:
            print(f"Cement Type: {ct:<5} | Not enough rows to train")
            continue

        model = models[ct]
        X = sub_df[ML_FEATURES]
        y = sub_df["Strength_28D"]
        _, X_test, _, y_test = train_test_split(X, y, test_size=0.20, random_state=42)
        preds = model.predict(X_test)
        r2 = r2_score(y_test, preds)
        mae = mean_absolute_error(y_test, preds)
        rmse = _rmse_fn(y_test, preds)
        trained_models[ct] = (model, X.mean())

        meta = ml_data[ct]
        print(
            f"Cement Type: {ct:<5} | Test Records: {len(y_test):<4} | "
            f"R²: {r2:<5.3f} | MAE: {mae:<5.2f} MPa | RMSE: {rmse:<5.2f} MPa | "
            f"Confidence: {meta['confidence']}"
        )
        importances = pd.Series(model.feature_importances_, index=ML_FEATURES).sort_values(ascending=False)
        top_3 = ", ".join(f"{k} ({round(v * 100)}%)" for k, v in importances.head(3).items())
        print(f"  • Top Drivers of 28D Strength: {top_3}")
        print("-" * 80)

    print("\n" + "=" * 80)
    print("TEST 3: PHYSICAL SENSITIVITY TEST (Sanity Checks on Hydration Physics)")
    print("=" * 80)

    if "OPC" in trained_models:
        model, mean_sample = trained_models["OPC"]
        baseline_x = pd.DataFrame([mean_sample])
        baseline_pred = model.predict(baseline_x)[0]
        print(f"Baseline OPC Recipe 28-Day Predicted Strength: {round(baseline_pred, 2)} MPa")
        print("-" * 80)

        for label, perturb in [
            ("Increase SSB Fineness by +500 cm²/g", lambda x: x.assign(Fineness=x["Fineness"] + 500)),
            ("Increase Early Strength by +5.0 MPa", lambda x: x.assign(Strength_Early=x["Strength_Early"] + 5)),
            ("Increase CaO +1.0%, decrease SiO2 -1.0%", lambda x: x.assign(CaO=x["CaO"] + 1, SiO2=x["SiO2"] - 1)),
        ]:
            x_new = perturb(baseline_x.copy())
            pred_new = model.predict(x_new)[0]
            diff = pred_new - baseline_pred
            print(f"Test: {label}")
            print(f"  • New Prediction: {round(pred_new, 2)} MPa (Change: {round(diff, 2)} MPa)")
            print("-" * 80)

    print("=" * 80)


if __name__ == "__main__":
    test_chemical_logic()
    test_ml_logic()
