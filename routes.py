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


# Helper to load .env in routes.py
def load_env():
    env_paths = [".env", "../.env"]
    for path in env_paths:
        if os.path.exists(path):
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line and not line.startswith("#"):
                        key, val = line.split("=", 1)
                        val = val.strip().strip("'").strip('"')
                        os.environ[key.strip()] = val

load_env()

rag_index = None

def get_rag_index():
    global rag_index
    if rag_index is None:
        index_path = "knowledge_base/rag_index.pkl"
        if os.path.exists(index_path):
            try:
                import pickle
                with open(index_path, 'rb') as f:
                    rag_index = pickle.load(f)
            except Exception as e:
                print(f"Error loading RAG index: {e}")
    return rag_index

@router.post("/api/chat")
async def chat(request: Request):
    try:
        body = await request.json()
        message = body.get("message", "").strip()
        history = body.get("history", [])

        if not message:
            raise HTTPException(status_code=400, detail="Empty message")

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="Gemini API Key is not configured on the server.")

        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=api_key)

        index = get_rag_index()
        retrieved_contexts = []
        sources = []

        if index and index.get("chunks") and index.get("vectorizer") is not None and index.get("tfidf_matrix") is not None:
            # 1. Transform query
            vectorizer = index["vectorizer"]
            tfidf_matrix = index["tfidf_matrix"]
            query_vec = vectorizer.transform([message])

            # 2. Compute similarity
            similarities = np.dot(tfidf_matrix, query_vec.T).toarray().flatten()

            # Get top 5
            top_k = min(5, len(similarities))
            top_indices = np.argsort(similarities)[::-1][:top_k]

            for idx in top_indices:
                score = float(similarities[idx])
                if score > 0.05: # Minimum similarity threshold
                    chunk = index["chunks"][idx]
                    retrieved_contexts.append(chunk["text"])
                    sources.append({
                        "file": chunk["source"],
                        "page": chunk["page"],
                        "score": round(score, 3)
                    })

        # Format the system instruction
        context_str = "\n\n".join([f"Document {i+1} (Source: {src['file']}, Page {src['page']}):\n{txt}" for i, (src, txt) in enumerate(zip(sources, retrieved_contexts))])
        
        system_instruction = (
            "You are an expert Cement Quality & Plant Operations Assistant. Your purpose is to help the lab technician troubleshoot cement strength anomalies, interpret raw mix design concepts, and find relevant standards.\n\n"
            "Using ONLY the provided reference documents below, answer the user's question. Be precise, concise, and cite which document and page you found the information in.\n"
            "If the answer cannot be found in the references, politely say that you do not have that information in the manuals/standards. Do NOT make up answers.\n\n"
            f"--- REFERENCE DOCUMENTS ---\n{context_str}\n---------------------------"
        )
        
        formatted_history = []
        for turn in history:
            role = "user" if turn.get("role") == "user" else "model"
            formatted_history.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=turn.get("content", ""))]
                )
            )
            
        chat_session = client.chats.create(
            model="gemini-2.5-flash",
            history=formatted_history
        )
        
        prompt = f"{system_instruction}\n\nUser Question: {message}"
        response = chat_session.send_message(message=prompt)
        
        # Deduplicate sources
        unique_sources = []
        seen = set()
        for src in sources:
            key = (src["file"], src["page"])
            if key not in seen:
                seen.add(key)
                unique_sources.append(src)
                
        return {
            "response": response.text,
            "sources": unique_sources
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/rag/rebuild")
def rebuild_rag_index():
    try:
        global rag_index
        # Force reload from disk next time get_rag_index() is called
        rag_index = None
        
        from rag_index import rebuild_index
        rebuild_index()
        return {"status": "success", "message": "RAG index rebuilt successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
