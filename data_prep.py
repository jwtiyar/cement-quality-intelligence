"""Load and normalize the consolidated cement CSV."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

CEMENT_TYPES = ["OPC", "SRC", "SBC"]
ML_EXCLUDED_YEARS = {2019}

NUMERIC_COLS = [
    "SiO2", "Al2O3", "Fe2O3", "CaO", "MgO", "SO3",
    "LSF", "C3S", "C2S", "C3A", "C4AF", "SM", "AM", "L.O.I", "Fineness",
    "Strength_Early", "Strength_7D", "Strength_28D", "Early_Strength_Days",
    "Residue_80",
]


def default_csv_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "ALL_CEMENT_DATA.csv")


def load_and_prepare(csv_path: str | None = None) -> pd.DataFrame:
    path = csv_path or default_csv_path()
    df = pd.read_csv(path)

    if "Cmp.St. Mpa_3 day" in df.columns and "3 day" in df.columns:
        df["Strength_3D"] = df["Cmp.St. Mpa_3 day"].combine_first(df["3 day"])
    elif "Cmp.St. Mpa_3 day" in df.columns:
        df["Strength_3D"] = df["Cmp.St. Mpa_3 day"]
    elif "3 day" in df.columns:
        df["Strength_3D"] = df["3 day"]
    else:
        df["Strength_3D"] = np.nan

    if "Cmp.St. Mpa_2 day" in df.columns and "2 day" in df.columns:
        df["Strength_2D"] = df["Cmp.St. Mpa_2 day"].combine_first(df["2 day"])
    elif "Cmp.St. Mpa_2 day" in df.columns:
        df["Strength_2D"] = df["Cmp.St. Mpa_2 day"]
    elif "2 day" in df.columns:
        df["Strength_2D"] = df["2 day"]
    else:
        df["Strength_2D"] = np.nan

    df["Strength_Early"] = df["Strength_3D"].combine_first(df["Strength_2D"])
    df["Early_Strength_Days"] = np.where(
        df["Strength_3D"].notna(),
        3,
        np.where(df["Strength_2D"].notna(), 2, np.nan),
    )

    # Collect all possible 28-day strength columns
    strength_28_cols = ["Cmp.St. Mpa_28 day", "28 day", "28 days"]
    available_28_cols = [c for c in strength_28_cols if c in df.columns]
    
    if available_28_cols:
        df["Strength_28D"] = df[available_28_cols[0]]
        for col in available_28_cols[1:]:
            df["Strength_28D"] = df["Strength_28D"].combine_first(df[col])
    else:
        df["Strength_28D"] = np.nan

    fin_cols = [c for c in df.columns if "SSB" in c]
    if fin_cols:
        df["Fineness"] = df[fin_cols[0]]
        for col in fin_cols[1:]:
            df["Fineness"] = df["Fineness"].combine_first(df[col])
    else:
        df["Fineness"] = np.nan

    # 7-day strength — the single strongest predictor of 28-day strength (r=+0.92)
    strength_7d_cols = [c for c in df.columns if "7 day" in c or c == "7D" or c == "7d"]
    if strength_7d_cols:
        df["Strength_7D"] = df[strength_7d_cols[0]]
        for col in strength_7d_cols[1:]:
            df["Strength_7D"] = df["Strength_7D"].combine_first(df[col])
    else:
        df["Strength_7D"] = np.nan

    # Sieve residue on 80 µm (%R80 / %R,80) — fineness proxy, r=-0.82 with 28D
    residue_cols = [c for c in df.columns if "%R" in c.upper()]
    if residue_cols:
        df["Residue_80"] = df[residue_cols[0]]
        for col in residue_cols[1:]:
            df["Residue_80"] = df["Residue_80"].combine_first(df[col])
    else:
        df["Residue_80"] = np.nan

    if "L.S.F" in df.columns:
        df["LSF"] = df["L.S.F"]

    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", "."), errors="coerce")

    df = df.dropna(subset=["Year", "Cement_Type"])
    df["Year"] = df["Year"].astype(int)
    df["Date_str"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["Date_dt"] = pd.to_datetime(df["Date"], errors="coerce")
    return df


def ml_training_frame(df: pd.DataFrame, cement_type: str) -> pd.DataFrame:
    """Rows eligible for 28-day strength model training."""
    return df[
        (df["Cement_Type"] == cement_type)
        & (~df["Year"].isin(ML_EXCLUDED_YEARS))
        & df["Strength_28D"].notna()
    ].copy()
