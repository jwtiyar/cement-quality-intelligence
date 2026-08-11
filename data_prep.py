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

    # LSF is stored as a ratio (0.91–1.00) in the Excel reports; the chemistry
    # API and raw-mix solver report it as a percentage (91–100). Canonical unit
    # is percentage everywhere — scale ratio values once at load time.
    if "LSF" in df.columns:
        df.loc[df["LSF"].notna() & (df["LSF"] < 2), "LSF"] *= 100.0

    # Compute LSF and C3S from oxides for rows where the Excel report omitted
    # those columns or left them blank. Many older reports only stored the basic
    # four oxides — the Bogue and LSF formulas give the same values the lab uses.
    oxide_cols = ["CaO", "SiO2", "Al2O3", "Fe2O3"]
    has_oxides = all(c in df.columns for c in oxide_cols)
    if has_oxides:
        so3 = df["SO3"].fillna(0) if "SO3" in df.columns else 0.0
        cao = df["CaO"]
        sio2 = df["SiO2"]
        al2o3 = df["Al2O3"]
        fe2o3 = df["Fe2O3"]

        denom_lsf = 2.8 * sio2 + 1.18 * al2o3 + 0.65 * fe2o3
        computed_lsf = 100.0 * (cao - 0.7 * so3) / denom_lsf.where(denom_lsf != 0, pd.NA)
        if "LSF" not in df.columns:
            df["LSF"] = computed_lsf
        else:
            df["LSF"] = df["LSF"].fillna(computed_lsf)

        so3_c3s = df["SO3"].fillna(0) if "SO3" in df.columns else 0.0
        computed_c3s = (
            4.071 * cao - 7.600 * sio2 - 6.718 * al2o3
            - 1.430 * fe2o3 - 2.852 * so3_c3s
        )
        if "C3S" not in df.columns:
            df["C3S"] = computed_c3s
        else:
            df["C3S"] = df["C3S"].fillna(computed_c3s)

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
