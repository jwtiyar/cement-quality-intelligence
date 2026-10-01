"""Calculations and filters for seasonal and quarterly averages of 28-day strength and C3S."""

from __future__ import annotations

from typing import Any
import pandas as pd

SEASONS_INFO = [
    {"key": "spring", "name": "Spring", "icon": "🌸", "label": "Mar – May", "months": [3, 4, 5]},
    {"key": "summer", "name": "Summer", "icon": "☀️", "label": "Jun – Aug", "months": [6, 7, 8]},
    {"key": "autumn", "name": "Autumn", "icon": "🍂", "label": "Sep – Nov", "months": [9, 10, 11]},
    {"key": "winter", "name": "Winter", "icon": "❄️", "label": "Dec – Feb", "months": [12, 1, 2]},
]

QUARTERS_INFO = [
    {"key": "Q1", "name": "Q1", "icon": "📅", "label": "Jan – Mar", "months": [1, 2, 3]},
    {"key": "Q2", "name": "Q2", "icon": "📅", "label": "Apr – Jun", "months": [4, 5, 6]},
    {"key": "Q3", "name": "Q3", "icon": "📅", "label": "Jul – Sep", "months": [7, 8, 9]},
    {"key": "Q4", "name": "Q4", "icon": "📅", "label": "Oct – Dec", "months": [10, 11, 12]},
]

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def compute_subset_stats(sub_df: pd.DataFrame, cement_types: tuple[str, ...] = ("OPC", "SRC", "SBC")) -> dict[str, Any]:
    """Compute 28-day strength and C3S averages and counts for a filtered DataFrame subset."""
    avg_strength: dict[str, float | None] = {}
    avg_c3s: dict[str, float | None] = {}
    sample_counts_28d: dict[str, int] = {}
    sample_counts_c3s: dict[str, int] = {}

    for c in cement_types:
        c_sub = sub_df[sub_df["Cement_Type"] == c]
        s28 = c_sub["Strength_28D"].dropna()
        c3s = c_sub["C3S"].dropna()
        avg_strength[c] = round(float(s28.mean()), 1) if not s28.empty else None
        avg_c3s[c] = round(float(c3s.mean()), 1) if not c3s.empty else None
        sample_counts_28d[c] = int(len(s28))
        sample_counts_c3s[c] = int(len(c3s))

    all_s28 = sub_df["Strength_28D"].dropna()
    all_c3s = sub_df["C3S"].dropna()
    avg_strength["overall"] = round(float(all_s28.mean()), 1) if not all_s28.empty else None
    avg_c3s["overall"] = round(float(all_c3s.mean()), 1) if not all_c3s.empty else None
    sample_counts_28d["overall"] = int(len(all_s28))
    sample_counts_c3s["overall"] = int(len(all_c3s))

    return {
        "totalRecords": int(len(sub_df)),
        "avgStrength": avg_strength,
        "avgC3S": avg_c3s,
        "sampleCounts": {
            "Strength_28D": sample_counts_28d,
            "C3S": sample_counts_c3s,
        },
    }


def get_averages_data(
    df: pd.DataFrame | None,
    period_type: str = "all",
    season: str | None = None,
    quarter: str | None = None,
    months: str | list[int] | None = None,
    year: str | int = "all",
) -> dict[str, Any]:
    """Filter dataset by period (season, quarter, or custom 3 months) and year, returning summary and breakdown."""
    if df is None or df.empty:
        return {}

    # 1. Base year filter
    year_filtered_df = df
    year_label = "All Years"
    if str(year).lower() != "all" and year is not None:
        try:
            y_int = int(year)
            year_filtered_df = df[df["Year"] == y_int]
            year_label = str(y_int)
        except (ValueError, TypeError):
            pass

    # 2. Period filter
    sub_df = year_filtered_df
    period_label = "Full Dataset (All Time)"
    active_months = None

    period_type_clean = (period_type or "all").lower()

    if period_type_clean == "season" and season:
        s_info = next((s for s in SEASONS_INFO if s["key"].lower() == str(season).lower()), None)
        if s_info:
            active_months = s_info["months"]
            sub_df = year_filtered_df[year_filtered_df["Month_Num"].isin(active_months)]
            period_label = f"{s_info['name']} ({s_info['label']})"
    elif period_type_clean == "quarter" and quarter:
        q_info = next((q for q in QUARTERS_INFO if q["key"].upper() == str(quarter).upper()), None)
        if q_info:
            active_months = q_info["months"]
            sub_df = year_filtered_df[year_filtered_df["Month_Num"].isin(active_months)]
            period_label = f"{q_info['name']} ({q_info['label']})"
    elif period_type_clean in ("months", "custom_3m") and months:
        if isinstance(months, str):
            month_list = [int(m.strip()) for m in months.split(",") if m.strip().isdigit()]
        else:
            month_list = [int(m) for m in months]
        if month_list:
            active_months = month_list
            sub_df = year_filtered_df[year_filtered_df["Month_Num"].isin(active_months)]
            names = [MONTH_NAMES[m - 1] for m in month_list if 1 <= m <= 12]
            period_label = f"Months: {' – '.join(names)}"

    full_label = f"{period_label} · {year_label}" if year_label != "All Years" else period_label

    if str(year).lower() != "all":
        coverage = f"Year {year_label}"
    elif not sub_df.empty and "Year" in sub_df.columns:
        coverage = f"{int(sub_df['Year'].min())} - {int(sub_df['Year'].max())}"
    else:
        coverage = "--"

    stats = compute_subset_stats(sub_df)

    # 3. Seasonal breakdown evaluated on year_filtered_df
    seasonal_breakdown = []
    for s in SEASONS_INFO:
        s_df = year_filtered_df[year_filtered_df["Month_Num"].isin(s["months"])]
        s_stats = compute_subset_stats(s_df)
        seasonal_breakdown.append({
            "key": s["key"],
            "name": s["name"],
            "icon": s["icon"],
            "label": s["label"],
            "months": s["months"],
            "totalRecords": s_stats["totalRecords"],
            "avgStrength": s_stats["avgStrength"],
            "avgC3S": s_stats["avgC3S"],
            "sampleCounts": s_stats["sampleCounts"],
        })

    # 4. Quarterly breakdown evaluated on year_filtered_df
    quarterly_breakdown = []
    for q in QUARTERS_INFO:
        q_df = year_filtered_df[year_filtered_df["Month_Num"].isin(q["months"])]
        q_stats = compute_subset_stats(q_df)
        quarterly_breakdown.append({
            "key": q["key"],
            "name": q["name"],
            "icon": q["icon"],
            "label": q["label"],
            "months": q["months"],
            "totalRecords": q_stats["totalRecords"],
            "avgStrength": q_stats["avgStrength"],
            "avgC3S": q_stats["avgC3S"],
            "sampleCounts": q_stats["sampleCounts"],
        })

    available_years = sorted(df["Year"].dropna().unique().astype(int).tolist(), reverse=True)

    return {
        "periodType": period_type,
        "periodLabel": full_label,
        "year": str(year),
        "activeMonths": active_months,
        "totalRecords": stats["totalRecords"],
        "yearsCoverage": coverage,
        "avgStrength": stats["avgStrength"],
        "avgC3S": stats["avgC3S"],
        "sampleCounts": stats["sampleCounts"],
        "seasonalBreakdown": seasonal_breakdown,
        "quarterlyBreakdown": quarterly_breakdown,
        "availableYears": available_years,
    }
