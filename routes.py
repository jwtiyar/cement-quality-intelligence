"""FastAPI route handlers."""

from __future__ import annotations

import calendar
import os
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse as FastFileResponse

from chemistry import OxideAnalysis, analyze_clinker, lsf_advice
from data_prep import default_csv_path
from ml_train import ML_FEATURES
from rawmix_solver import calculate_rawmix
import state

router = APIRouter()


@router.get("/api/data")
def get_data():
    return state.data_cache


@router.get("/api/record")
def get_record(date: str, type: str = "OPC"):
    if state.df_global is None:
        raise HTTPException(status_code=503, detail="Dataset not loaded")
    try:
        target_date = pd.to_datetime(date).strftime("%Y-%m-%d")
        row = state.df_global[(state.df_global["Date_str"] == target_date) & (state.df_global["Cement_Type"] == type)]
        if row.empty:
            return {"found": False}

        record = row.iloc[0].to_dict()
        clean_record = {}
        for k, v in record.items():
            if pd.isna(v):
                clean_record[k] = None
            elif isinstance(v, (np.integer, np.floating)):
                clean_record[k] = float(v) if isinstance(v, np.floating) else int(v)
            else:
                clean_record[k] = str(v)
        return {"found": True, "record": clean_record}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/latest_date")
def get_latest_date(type: str = "OPC"):
    if state.df_global is None:
        raise HTTPException(status_code=503, detail="Dataset not loaded")
    try:
        df_type = state.df_global[(state.df_global["Cement_Type"] == type) & state.df_global["Date_str"].notna()]
        if df_type.empty:
            return {"found": False}
        latest_row = df_type.sort_values("Date_dt", ascending=False).iloc[0]
        return {"found": True, "date": latest_row["Date_str"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/monthly")
def get_monthly(year: int, month: int, param: str = "Strength_28D"):
    if state.df_global is None:
        raise HTTPException(status_code=503, detail="Dataset not loaded")
    try:
        _, num_days = calendar.monthrange(year, month)
        days = list(range(1, num_days + 1))

        mask = (state.df_global["Date_dt"].dt.year == year) & (state.df_global["Date_dt"].dt.month == month)
        df_month = state.df_global[mask].dropna(subset=[param, "Date_dt", "Cement_Type"]).copy()
        df_month["Day"] = df_month["Date_dt"].dt.day
        daily_avg = df_month.groupby(["Day", "Cement_Type"])[param].mean().reset_index()

        pivot = daily_avg.pivot(index="Day", columns="Cement_Type", values=param).reindex(days)
        pivot = pivot.replace({np.nan: None})

        return {
            "labels": [str(d) for d in days],
            "OPC": pivot["OPC"].tolist() if "OPC" in pivot.columns else [None] * len(days),
            "SRC": pivot["SRC"].tolist() if "SRC" in pivot.columns else [None] * len(days),
            "SBC": pivot["SBC"].tolist() if "SBC" in pivot.columns else [None] * len(days),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/chemistry/analyze")
async def chemistry_analyze(request: Request):
    try:
        body = await request.json()
        ox = OxideAnalysis(
            SiO2=float(body.get("SiO2", 0)),
            Al2O3=float(body.get("Al2O3", 0)),
            Fe2O3=float(body.get("Fe2O3", 0)),
            CaO=float(body.get("CaO", 0)),
            MgO=float(body.get("MgO", 0)),
            SO3=float(body.get("SO3", 0)),
        )
        result = analyze_clinker(ox)
        lsf_pct = result["moduli"]["LSF"]
        return {
            **result,
            "advice": lsf_advice(lsf_pct),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/predict")
async def predict(request: Request):
    try:
        inputs = await request.json()
        c_type = inputs.get("Cement_Type", "OPC")

        if c_type not in state.xgb_models:
            ml_info = state.data_cache.get("ml", {}).get(c_type, {})
            raise HTTPException(
                status_code=400,
                detail=f"No model for '{c_type}' ({ml_info.get('trainSamples', 0)} training rows)",
            )

        model = state.xgb_models[c_type]
        features_val = []
        for feat in ML_FEATURES:
            val = inputs.get(feat, state.data_cache["ml"][c_type]["averages"][feat])
            features_val.append(float(val))

        pred_df = pd.DataFrame([features_val], columns=ML_FEATURES)
        pred = float(model.predict(pred_df)[0])
        ml_meta = state.data_cache["ml"][c_type]

        return {
            "prediction": round(pred, 2),
            "confidence": ml_meta["confidence"],
            "confidenceLabel": ml_meta["confidenceLabel"],
            "r2": ml_meta["r2"],
            "rmse": ml_meta["rmse"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/rawmix/calculate")
async def rawmix_calculate(request: Request):
    try:
        body = await request.json()
        return calculate_rawmix(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/refresh")
def refresh_data():
    """Re-scan Excel workbooks, rebuild CSV, retrain models in memory."""
    try:
        from build_dataset import extract_data

        csv_path = default_csv_path()
        old_keys: set[str] = set()
        if os.path.exists(csv_path):
            old_df = pd.read_csv(csv_path)
            if not old_df.empty and "Date" in old_df.columns and "Cement_Type" in old_df.columns:
                old_keys = {
                    str(row["Date"]) + "_" + str(row["Cement_Type"])
                    for _, row in old_df.iterrows()
                }

        extract_data()

        new_records = []
        if os.path.exists(csv_path):
            new_df = pd.read_csv(csv_path)
            if not new_df.empty and "Date" in new_df.columns and "Cement_Type" in new_df.columns:
                for _, row in new_df.iterrows():
                    key = str(row["Date"]) + "_" + str(row["Cement_Type"])
                    if key not in old_keys:
                        new_records.append({"date": row["Date"], "type": row["Cement_Type"]})

        state.reload_from_csv(csv_path)
        return {
            "status": "success",
            "new_records": new_records,
            "dataset": state.data_cache.get("dataset", {}),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/export/csv")
def export_csv():
    """Download the consolidated cement dataset as CSV."""
    csv_path = default_csv_path()
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=404, detail="CSV dataset not found")
    return FastFileResponse(
        csv_path,
        media_type="text/csv",
        filename="ALL_CEMENT_DATA.csv",
        headers={"Content-Disposition": "attachment; filename=ALL_CEMENT_DATA.csv"},
    )
