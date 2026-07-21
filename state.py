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


def get_live_dataset_summary(df: pd.DataFrame | None = None) -> str:
    """Return a detailed, structured summary of plant dataset for LLM chat context."""
    if df is None:
        df = df_global
    if df is None or df.empty:
        return "No live laboratory dataset loaded."

    valid_df = df.dropna(subset=["Date_dt"]).sort_values("Date_dt", ascending=False)
    if valid_df.empty:
        return "No dated laboratory records found."

    earliest = valid_df["Date_dt"].min().strftime("%Y-%m-%d")
    latest = valid_df["Date_dt"].max().strftime("%Y-%m-%d")
    total_records = len(df)

    lines = []
    lines.append("=== LIVE PLANT LABORATORY DATASET SUMMARY ===")
    lines.append(f"Total Daily Laboratory Records: {total_records}")
    lines.append(f"Data Coverage Range: {earliest} to {latest} (Latest Date: {latest})")

    # Overall averages per cement type
    lines.append("\n--- OVERALL HISTORICAL AVERAGES PER CEMENT TYPE ---")
    for ctype in sorted(df["Cement_Type"].unique()):
        sub = df[df["Cement_Type"] == ctype]
        s28_avg = sub["Strength_28D"].mean()
        se_avg = sub["Strength_Early"].mean()
        fin_avg = sub["Fineness"].mean()
        lsf_avg = sub["LSF"].mean()
        c3s_avg = sub["C3S"].mean()

        lsf_disp = lsf_avg * 100 if (pd.notna(lsf_avg) and lsf_avg < 2) else lsf_avg
        lines.append(
            f"• [{ctype}] ({len(sub)} tests): 28D Strength Avg={s28_avg:.1f} MPa | "
            f"Early Strength Avg={se_avg:.1f} MPa | Blaine Avg={fin_avg:.0f} cm²/g | "
            f"LSF Avg={lsf_disp:.1f}% | C3S Avg={c3s_avg:.1f}%"
        )

    # Monthly Summary (All available months in recent 24 months)
    lines.append("\n--- MONTHLY STRENGTH & QUALITY AVERAGES (LAST 24 MONTHS) ---")
    valid_df_copy = valid_df.copy()
    valid_df_copy["YM"] = valid_df_copy["Date_dt"].dt.to_period("M")
    unique_yms = sorted(valid_df_copy["YM"].unique(), reverse=True)[:24]

    for ym in unique_yms:
        ym_df = valid_df_copy[valid_df_copy["YM"] == ym]
        for ctype in sorted(ym_df["Cement_Type"].unique()):
            sub = ym_df[ym_df["Cement_Type"] == ctype]
            s28_vals = sub["Strength_28D"].dropna()
            se_vals = sub["Strength_Early"].dropna()
            fin_vals = sub["Fineness"].dropna()
            lsf_vals = sub["LSF"].dropna()

            s28_str = f"Avg={s28_vals.mean():.1f} MPa (Min={s28_vals.min():.1f}, Max={s28_vals.max():.1f})" if not s28_vals.empty else "N/A"
            se_str = f"Avg={se_vals.mean():.1f} MPa" if not se_vals.empty else "N/A"
            fin_str = f"Avg={fin_vals.mean():.0f} cm²/g" if not fin_vals.empty else "N/A"
            if not lsf_vals.empty:
                m_lsf = lsf_vals.mean()
                disp_lsf = m_lsf * 100 if m_lsf < 2 else m_lsf
                lsf_str = f"LSF={disp_lsf:.1f}%"
            else:
                lsf_str = "N/A"

            lines.append(
                f"• {ym} | {ctype} ({len(sub)} records) -> 28D Strength: {s28_str} | "
                f"Early Strength: {se_str} | Blaine: {fin_str} | {lsf_str}"
            )

    # Weekly Summary (Recent 12 Weeks)
    lines.append("\n--- RECENT WEEKLY STRENGTH AVERAGES (LAST 12 WEEKS) ---")
    valid_df_copy["YW"] = valid_df_copy["Date_dt"].dt.to_period("W")
    unique_yws = sorted(valid_df_copy["YW"].unique(), reverse=True)[:12]

    for yw in unique_yws:
        yw_df = valid_df_copy[valid_df_copy["YW"] == yw]
        for ctype in sorted(yw_df["Cement_Type"].unique()):
            sub = yw_df[yw_df["Cement_Type"] == ctype]
            s28_vals = sub["Strength_28D"].dropna()
            se_vals = sub["Strength_Early"].dropna()
            fin_vals = sub["Fineness"].dropna()

            s28_str = f"{s28_vals.mean():.1f} MPa" if not s28_vals.empty else "N/A"
            se_str = f"{se_vals.mean():.1f} MPa" if not se_vals.empty else "N/A"
            fin_str = f"{fin_vals.mean():.0f} cm²/g" if not fin_vals.empty else "N/A"

            start_str = yw.start_time.strftime("%Y-%m-%d")
            end_str = yw.end_time.strftime("%Y-%m-%d")
            lines.append(
                f"• Week {start_str} to {end_str} | {ctype} ({len(sub)} records) -> "
                f"28D Strength: {s28_str} | Early Strength: {se_str} | Blaine: {fin_str}"
            )

    # Recent Daily Test Records (Latest 60 Daily Tests)
    lines.append("\n--- LATEST DAILY LABORATORY TEST RESULTS (MOST RECENT 60 TEST DAYS) ---")
    lines.append("(Note: The most recent 2-3 days may show 'Pending Curing / 2-3 Day Test in Progress' because cement cubes take time to cure before crushing.)")
    recent_60 = valid_df.head(60)
    for _, row in recent_60.iterrows():
        d_str = str(row["Date_str"])
        ctype = row["Cement_Type"]
        
        s28_raw = row.get("Strength_28D")
        s28 = f"{s28_raw:.1f} MPa" if pd.notna(s28_raw) else "Pending 28D Curing"
        
        se_raw = row.get("Strength_Early")
        se = f"{se_raw:.1f} MPa" if pd.notna(se_raw) else "Pending Early Curing"
        
        fin = f"{row['Fineness']:.0f} cm²/g" if pd.notna(row.get("Fineness")) else "N/A"
        lsf_raw = row.get("LSF", 0)
        lsf_val = lsf_raw * 100 if (pd.notna(lsf_raw) and lsf_raw < 2) else lsf_raw
        lsf_str = f"{lsf_val:.1f}%" if pd.notna(lsf_raw) else "N/A"
        c3s = f"{row.get('C3S', 0):.1f}%" if pd.notna(row.get("C3S")) else "N/A"
        cao = f"{row.get('CaO', 0):.1f}%" if pd.notna(row.get("CaO")) else "N/A"
        so3 = f"{row.get('SO3', 0):.2f}%" if pd.notna(row.get("SO3")) else "N/A"

        lines.append(
            f"Date: {d_str} | Type: {ctype} | 28D Strength: {s28} | Early Strength: {se} | "
            f"Blaine: {fin} | LSF: {lsf_str} | C3S: {c3s} | CaO: {cao} | SO3: {so3}"
        )

    return "\n".join(lines)


def write_dataset_summary_to_file(df: pd.DataFrame) -> None:
    """Generate a clean text summary of historical daily results and save to knowledge_base."""
    os.makedirs("knowledge_base", exist_ok=True)
    summary_path = os.path.join("knowledge_base", "latest_daily_results.txt")
    
    summary_text = get_live_dataset_summary(df)
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_text)


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
