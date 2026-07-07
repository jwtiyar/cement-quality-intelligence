"""Application state: reload CSV, retrain models in memory, build API cache."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from data_prep import CEMENT_TYPES, default_csv_path, load_and_prepare
from ml_train import ML_FEATURES, train_all_models

ANOMALY_BOUNDS = {
    "SiO2": (17, 26),        # ASTM/EN typical: 19-23%
    "Al2O3": (2, 8),         # ASTM/EN typical: 3-6%
    "Fe2O3": (1, 6),         # ASTM/EN typical: 1.5-4.5%
    "CaO": (55, 70),         # ASTM/EN typical: 61-67%
    "MgO": (0, 6),           # ASTM C150 max is 6.0%
    "SO3": (0.5, 4.5),       # EN 197 max is 3.5%-4.0%, ASTM C150 max 3.0-4.5%
    "Strength_28D": (20, 80),# EN 197 classes: 32.5, 42.5, 52.5 MPa
    "Fineness": (2000, 6000),# Typical Blaine 2500-5000 cm2/g
    "C3S": (30, 80),         # Bogue typical
    "C3A": (0, 15)           # ASTM Type V max 5%, Type I up to 15%
}

data_cache: dict[str, Any] = {}
xgb_models: dict[str, Any] = {}
df_global: pd.DataFrame | None = None


def _chart_series(series: pd.Series) -> list[float | None]:
    return [None if pd.isna(v) else float(v) for v in series]


def _find_latest_month(df: pd.DataFrame) -> dict[str, int | None]:
    """Return {year, month} of the most recent record with any data."""
    valid = df.dropna(subset=["Date_dt"])
    if valid.empty:
        return {"year": None, "month": None}
    latest = valid["Date_dt"].max()
    return {"year": int(latest.year), "month": int(latest.month)}


def _find_28d_era_start(df: pd.DataFrame) -> int | None:
    """Return the first year where ≥50% of records have 28-day strength data."""
    for year in sorted(df["Year"].unique()):
        yr_df = df[df["Year"] == year]
        if yr_df.empty:
            continue
        ratio = yr_df["Strength_28D"].notna().mean()
        if ratio >= 0.5:
            return int(year)
    return None


def write_dataset_summary_to_file(df: pd.DataFrame) -> None:
    """Generate a clean text summary of historical daily results and save to knowledge_base."""
    os.makedirs("knowledge_base", exist_ok=True)
    summary_path = os.path.join("knowledge_base", "latest_daily_results.txt")
    
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("=== CEMENT PLANT LIVE QUALITY & DAILY REPORTS DATA SUMMARY ===\n")
        f.write(f"Report Generated At: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"Total Daily Laboratory Records: {len(df)} records\n")
        f.write(f"Years Covered: {df['Year'].min()} to {df['Year'].max()}\n\n")
        
        f.write("--- CEMENT TYPE RECORD COUNTS ---\n")
        for ctype, count in df["Cement_Type"].value_counts().items():
            f.write(f"- {ctype}: {count} daily records\n")
        f.write("\n")
        
        f.write("--- OVERALL HISTORICAL QUALITY AVERAGES ---\n")
        for ctype in sorted(df["Cement_Type"].unique()):
            sub = df[df["Cement_Type"] == ctype]
            f.write(f"\n[{ctype} averages]:\n")
            f.write(f"  - 28-Day Strength: {sub['Strength_28D'].mean():.2f} MPa (Averaged over {sub['Strength_28D'].notna().sum()} records)\n")
            f.write(f"  - 3-Day/Early Strength: {sub['Strength_Early'].mean():.2f} MPa\n")
            f.write(f"  - Blaine Fineness (SSB): {sub['Fineness'].mean():.1f} cm2/g\n")
            f.write(f"  - CaO: {sub['CaO'].mean():.2f}%, SiO2: {sub['SiO2'].mean():.2f}%, Al2O3: {sub['Al2O3'].mean():.2f}%, Fe2O3: {sub['Fe2O3'].mean():.2f}%\n")
            f.write(f"  - SO3: {sub['SO3'].mean():.2f}%, MgO: {sub['MgO'].mean():.2f}%\n")
            f.write(f"  - Lime Saturation Factor (LSF): {sub['LSF'].mean():.4f}, SM: {sub['SM'].mean():.4f}, AM: {sub['AM'].mean():.4f}\n")
            f.write(f"  - Bogue Phases: C3S={sub['C3S'].mean():.2f}%, C2S={sub['C2S'].mean():.2f}%, C3A={sub['C3A'].mean():.2f}%, C4AF={sub['C4AF'].mean():.2f}%\n")
            
        f.write("\n--- RECENT DAILY LABORATORY RESULTS (LATEST 30 RECORDS) ---\n")
        # Sort by date descending and get top 30
        recent = df.dropna(subset=["Date_dt"]).sort_values("Date_dt", ascending=False).head(30)
        for _, row in recent.iterrows():
            date_str = str(row["Date_str"])
            f.write(f"\nDate: {date_str} | Cement Type: {row['Cement_Type']}\n")
            f.write(f"  Chemical: CaO={row.get('CaO', 0):.2f}%, SiO2={row.get('SiO2', 0):.2f}%, Al2O3={row.get('Al2O3', 0):.2f}%, Fe2O3={row.get('Fe2O3', 0):.2f}%, SO3={row.get('SO3', 0):.2f}%, MgO={row.get('MgO', 0):.2f}%\n")
            f.write(f"  Moduli: LSF={row.get('LSF', 0):.4f}, SM={row.get('SM', 0):.4f}, AM={row.get('AM', 0):.4f}\n")
            f.write(f"  Bogue: C3S={row.get('C3S', 0):.2f}%, C2S={row.get('C2S', 0):.2f}%, C3A={row.get('C3A', 0):.2f}%, C4AF={row.get('C4AF', 0):.2f}%\n")
            f.write(f"  Physical: Fineness={row.get('Fineness', 0):.1f} cm2/g | Early Strength={row.get('Strength_Early', 0):.2f} MPa | 28D Strength={row.get('Strength_28D', 0):.2f} MPa\n")


def reload_from_csv(csv_path: str | None = None) -> None:
    """
    Load latest CSV, retrain all ML models in memory, rebuild dashboard cache.

    Called on every server start and after Excel sync — models are never saved to disk
    because new lab data arrives daily/weekly.
    """
    global data_cache, xgb_models, df_global

    path = csv_path or default_csv_path()
    print("Loading and cleaning dataset...")
    df = load_and_prepare(path)
    df_global = df

    # Save a text summary report for RAG assistant awareness
    try:
        write_dataset_summary_to_file(df)
        print("Dataset text summary updated in knowledge_base/latest_daily_results.txt")
    except Exception as e:
        print(f"Error saving dataset text summary: {e}")

    xgb_models, ml_data = train_all_models(df)

    trends: dict[str, dict[str, list]] = {}
    chart_params = ["Strength_28D", "Strength_Early", "C3S", "CaO", "Fineness", "LSF"]
    years = sorted(df["Year"].unique().tolist())

    for param in chart_params:
        if param not in df.columns:
            continue
        yearly_avg = df.groupby(["Year", "Cement_Type"])[param].mean().reset_index()
        pivot = yearly_avg.pivot(index="Year", columns="Cement_Type", values=param).reindex(years)
        trends[param] = {
            c: _chart_series(pivot[c]) if c in pivot.columns else [None] * len(years)
            for c in CEMENT_TYPES
        }

    df_opc = df[df["Cement_Type"] == "OPC"].copy()
    corr_cols = ["Strength_28D", "Strength_Early", "C3S", "Fineness", "CaO", "SiO2", "LSF", "SO3"]
    corr_matrix = df_opc[corr_cols].corr().fillna(0).to_dict()

    low_strength = df.dropna(subset=["Strength_28D"]).sort_values("Strength_28D").head(10)
    low_strength_list = []
    for _, row in low_strength.iterrows():
        low_strength_list.append({
            "Date": str(row["Date"]).split(" ")[0],
            "Type": str(row["Cement_Type"]),
            "Strength": round(float(row["Strength_28D"]), 1),
            "C3S": round(float(row["C3S"]), 1) if not pd.isna(row["C3S"]) else "N/A",
            "Fineness": int(row["Fineness"]) if not pd.isna(row["Fineness"]) else "N/A",
        })

    type_counts = {str(k): int(v) for k, v in df["Cement_Type"].value_counts().to_dict().items()}

    csv_mtime = None
    if os.path.exists(path):
        csv_mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).isoformat()

    strength_28_count = int(df["Strength_28D"].notna().sum())

    anomalies = []
    for param, (low, high) in ANOMALY_BOUNDS.items():
        if param in df.columns:
            s_numeric = pd.to_numeric(df[param], errors='coerce')
            mask = s_numeric.notna() & ((s_numeric < low) | (s_numeric > high))
            outliers = df[mask]
            for _, row in outliers.iterrows():
                anomalies.append({
                    "Date": str(row["Date_str"]),
                    "Type": str(row.get("Cement_Type", "Unknown")),
                    "Parameter": param,
                    "Value": round(float(row[param]), 2),
                    "Expected": f"{low} - {high}"
                })

    data_cache = {
        "summary": {
            "totalRecords": len(df),
            "strength28Records": strength_28_count,
            "avgStrength": {
                c: round(float(df[df["Cement_Type"] == c]["Strength_28D"].mean()), 1)
                if not df[df["Cement_Type"] == c]["Strength_28D"].dropna().empty
                else 0
                for c in CEMENT_TYPES
            },
            "avgC3S": {
                c: round(float(df[df["Cement_Type"] == c]["C3S"].mean()), 1)
                if not df[df["Cement_Type"] == c]["C3S"].dropna().empty
                else 0
                for c in CEMENT_TYPES
            },
            "yearsCoverage": f"{df['Year'].min()} - {df['Year'].max()}",
        },
        "dataset": {
            "csvLastModified": csv_mtime,
            "retrainPolicy": "Models retrained in memory on every startup and Excel sync",
            "mlExcludedYears": sorted({2019}),
            "strength28Note": (
                "Pre-~2018 rows often have 2D/3D/7D strength only; "
                "28-day training uses rows where 28D exists (~{n} rows).".format(n=strength_28_count)
            ),
        },
        "trends": {"labels": [str(y) for y in years], "data": trends},
        "correlation": {"columns": corr_cols, "matrix": corr_matrix},
        "lowStrengthDays": low_strength_list,
        "anomalies": anomalies,
        "distribution": type_counts,
        "ml": ml_data,
        "mlFeatures": ML_FEATURES,
        "latestDataMonth": _find_latest_month(df),
        "strength28Era": _find_28d_era_start(df),
    }

    print(f"Cache ready: {len(df)} records, CSV mtime {csv_mtime}")
