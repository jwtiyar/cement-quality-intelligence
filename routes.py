"""FastAPI route handlers with request-scoped state snapshots and timeout safety."""

from __future__ import annotations

import asyncio
import calendar
import os
from typing import Any

import anyio
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from chemistry import OxideAnalysis, analyze_clinker, lsf_advice
from codex_provider import CodexProviderError, ask_codex
from data_prep import default_csv_path
from ml_train import ML_FEATURES
from rawmix_solver import calculate_rawmix
from schemas import (
    ChatRequest,
    ChemistryAnalyzeRequest,
    PredictRequest,
    RawMixRequest,
)
import state
from typesafe_ai import assess_prediction, judge_rawmix, rerank_contexts

router = APIRouter()
CHAT_TIMEOUT_SECONDS = 35.0


async def _typesafe_call(fn, *args):
    if not os.environ.get("TYPESAFE_API_KEY"):
        return fn(*args)
    task = asyncio.create_task(anyio.to_thread.run_sync(fn, *args, abandon_on_cancel=True))
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=0.05)
        return task.result()
    finally:
        if not task.done():
            task.cancel()


@router.get("/api/data")
async def get_data():
    snapshot = state.get_snapshot()
    return snapshot.data_cache


@router.get("/api/record")
async def get_record(date: str, type: str = "OPC"):
    snapshot = state.get_snapshot()
    if snapshot.df is None or snapshot.df.empty:
        raise HTTPException(status_code=503, detail="Dataset not loaded")
    try:
        target_date = pd.to_datetime(date).strftime("%Y-%m-%d")
        row = snapshot.df[(snapshot.df["Date_str"] == target_date) & (snapshot.df["Cement_Type"] == type)]
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
async def get_latest_date(type: str = "OPC"):
    snapshot = state.get_snapshot()
    if snapshot.df is None or snapshot.df.empty:
        raise HTTPException(status_code=503, detail="Dataset not loaded")
    try:
        df_type = snapshot.df[(snapshot.df["Cement_Type"] == type) & snapshot.df["Date_str"].notna()]
        if df_type.empty:
            return {"found": False}
        latest_row = df_type.sort_values("Date_dt", ascending=False).iloc[0]
        return {"found": True, "date": latest_row["Date_str"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/monthly")
async def get_monthly(year: int, month: int, param: str = "Strength_28D"):
    snapshot = state.get_snapshot()
    if snapshot.df is None or snapshot.df.empty:
        raise HTTPException(status_code=503, detail="Dataset not loaded")
    try:
        _, num_days = calendar.monthrange(year, month)
        days = list(range(1, num_days + 1))

        mask = (snapshot.df["Date_dt"].dt.year == year) & (snapshot.df["Date_dt"].dt.month == month)
        df_month = snapshot.df[mask].dropna(subset=[param, "Date_dt", "Cement_Type"]).copy()
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
async def chemistry_analyze(body: ChemistryAnalyzeRequest):
    try:
        ox = OxideAnalysis(
            SiO2=body.SiO2,
            Al2O3=body.Al2O3,
            Fe2O3=body.Fe2O3,
            CaO=body.CaO,
            MgO=body.MgO,
            Na2O=body.Na2O,
            K2O=body.K2O,
            SO3=body.SO3,
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
async def predict(body: PredictRequest):
    try:
        snapshot = state.get_snapshot()
        c_type = body.Cement_Type
        ml_meta = snapshot.data_cache.get("ml", {}).get(c_type, {})

        if c_type not in snapshot.xgb_models or not ml_meta.get("hasModel", False):
            # Fall back to recentAverage baseline if trained model is absent
            if ml_meta.get("recentAverage") is not None:
                pred = float(ml_meta["recentAverage"])
                typesafe = {
                    "enabled": False,
                    "safe_to_show": None,
                    "probability": None,
                    "status": "not_reviewed",
                }
                return {
                    "prediction": round(pred, 2),
                    "prediction_source": "recent_mean",
                    "predictionSource": "recent_mean",
                    "recentAverage": round(pred, 2),
                    "mlPrediction": None,
                    "confidence": ml_meta.get("confidence", "insufficient_evidence"),
                    "confidenceLabel": ml_meta.get("confidenceLabel", "Recent baseline guidance"),
                    "r2": ml_meta.get("r2"),
                    "rmse": ml_meta.get("rmse"),
                    "typesafe": typesafe,
                }
            raise HTTPException(
                status_code=400,
                detail=f"No model or baseline for '{c_type}' ({ml_meta.get('trainSamples', 0)} training rows)",
            )

        model = snapshot.xgb_models[c_type]
        features_val = []
        for feat in ML_FEATURES:
            val = getattr(body, feat)
            if val is None:
                val = ml_meta["averages"][feat]
            features_val.append(float(val))

        pred_df = pd.DataFrame([features_val], columns=ML_FEATURES)
        ml_prediction = float(model.predict(pred_df)[0])

        use_recent_baseline = not ml_meta.get("modelBeatsRecentBaseline", False)
        pred = float(ml_meta["recentAverage"]) if use_recent_baseline and ml_meta.get("recentAverage") is not None else ml_prediction
        prediction_source = "recent_mean" if use_recent_baseline else "xgboost"
        confidence_label = (
            "Recent baseline guidance — ML confidence low"
            if use_recent_baseline
            else ml_meta["confidenceLabel"]
        )

        typesafe = {
            "enabled": False,
            "safe_to_show": None,
            "probability": None,
            "status": "not_reviewed",
        }
        if not use_recent_baseline:
            typesafe = await _typesafe_call(
                assess_prediction,
                c_type,
                pred,
                ml_meta["confidence"],
                ml_meta["r2"],
                ml_meta["rmse"],
            )

        return {
            "prediction": round(pred, 2),
            "prediction_source": prediction_source,
            "predictionSource": prediction_source,
            "recentAverage": round(float(ml_meta["recentAverage"]), 2) if ml_meta.get("recentAverage") is not None else None,
            "mlPrediction": round(ml_prediction, 2),
            "confidence": ml_meta["confidence"],
            "confidenceLabel": confidence_label,
            "r2": ml_meta["r2"],
            "rmse": ml_meta["rmse"],
            "typesafe": typesafe,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/rawmix/calculate")
async def rawmix_calculate(body: RawMixRequest):
    try:
        result = calculate_rawmix(body.model_dump())
        result["typesafe"] = await _typesafe_call(
            judge_rawmix,
            body.cement_type,
            result["clinker"],
            result["diagnostics"],
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/refresh")
async def refresh_data(allow_deletions: bool = False):
    """Transactional refresh: stage, validate completeness, retrain, atomic swap."""
    try:
        timed_out = False

        def cancellation_check() -> bool:
            return timed_out

        async with asyncio.timeout(120.0):
            snapshot = await state.refresh_dataset_transactional(
                allow_deletions=allow_deletions,
                cancellation_check=cancellation_check,
            )

        reload_rag_index()
        return {
            "status": "success",
            "dataset": snapshot.data_cache.get("dataset", {}),
            "dataset_version": snapshot.dataset_version,
            "records": len(snapshot.df),
        }
    except TimeoutError:
        timed_out = True
        raise HTTPException(
            status_code=504,
            detail="Dataset refresh timed out (120s limit). Live dataset was preserved without changes.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/export/csv")
async def export_csv():
    """Download the consolidated cement dataset as CSV."""
    csv_path = default_csv_path()
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=404, detail="CSV dataset not found")
    with open(csv_path, "rb") as csv_file:
        return Response(
            content=csv_file.read(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=ALL_CEMENT_DATA.csv"},
        )


# Helper to load .env in routes.py
def load_env(paths: list[str] | None = None) -> None:
    env_paths = paths or ["~/.config/cement-app/.env", ".env", "../.env"]
    for path in env_paths:
        path = os.path.expanduser(path)
        if os.path.exists(path):
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    val = val.split(" #", 1)[0] if " #" in val else val
                    val = val.strip().strip("'").strip('"')
                    os.environ.setdefault(key.strip(), val)


load_env()

rag_index = None


def reload_rag_index():
    global rag_index
    rag_index = None
    return get_rag_index()


def get_rag_index():
    global rag_index
    if rag_index is None:
        index_path = os.environ.get("RAG_INDEX_PATH", "knowledge_base/rag_index.pkl")
        if os.path.exists(index_path):
            try:
                import pickle
                with open(index_path, "rb") as f:
                    candidate = pickle.load(f)
                if not isinstance(candidate, dict) or not {"chunks", "vectorizer", "tfidf_matrix"} <= set(candidate):
                    print("RAG index has unexpected structure; ignoring")
                else:
                    rag_index = candidate
            except Exception as e:
                print(f"Error loading RAG index: {e}")
    return rag_index


def ml_reliability_context(prediction_context=None) -> str:
    snapshot = state.get_snapshot()
    lines = []
    for cement_type, meta in sorted(snapshot.data_cache.get("ml", {}).items()):
        r2_val = meta.get("r2")
        rmse_val = meta.get("rmse")
        r2_str = f"{r2_val:.2f}" if r2_val is not None else "n/a"
        rmse_str = f"{rmse_val:.2f}" if rmse_val is not None else "n/a"
        lines.append(
            f"{cement_type}: {meta.get('confidenceLabel', meta.get('confidence', 'unknown'))}; "
            f"validation R² {r2_str}, RMSE {rmse_str} MPa."
        )

    if prediction_context is None:
        lines.append("No optimizer prediction is attached to this chat request.")
    else:
        review = prediction_context.typesafe
        if review.status == "rejected" or review.safe_to_show is False:
            review_text = (
                f"TypeSafe safe-to-show=False ({review.probability:.0%})"
                if review.probability is not None
                else "TypeSafe safe-to-show=False"
            )
            status = "HELD FOR QUALIFIED REVIEW"
        elif review.status == "approved" or review.safe_to_show is True:
            prob_str = f" ({review.probability:.0%})" if review.probability is not None else ""
            review_text = f"TypeSafe safe-to-show=True{prob_str}"
            status = "APPROVED FOR DECISION SUPPORT"
        else:
            review_text = "TypeSafe safe-to-show=not_reviewed"
            status = "UNREVIEWED GUIDANCE"

        pred_r2 = f"{prediction_context.r2:.2f}" if prediction_context.r2 is not None else "n/a"
        pred_rmse = f"{prediction_context.rmse:.2f}" if prediction_context.rmse is not None else "n/a"

        lines.append(
            f"Latest optimizer result: {prediction_context.cement_type} {prediction_context.prediction:.2f} MPa "
            f"(source: {prediction_context.prediction_source}); {prediction_context.confidence_label}; "
            f"validation R² {pred_r2}, RMSE {pred_rmse} MPa; "
            f"{review_text}; status: {status}."
        )

    lines.append(
        "Treat chemistry_only, unreviewed, and held results as unreliable strength predictions, and exploratory results as uncertain. "
        "Explain their validation limits; "
        "never present them as production recommendations. TypeSafe is advisory; deterministic chemistry and plant controls remain authoritative."
    )
    return "\n".join(lines)


def _call_gemini_sync(api_key: str, formatted_history: list, prompt: str) -> str:
    from google import genai
    client = genai.Client(api_key=api_key)
    chat_session = client.chats.create(
        model="gemini-3.8-flash",
        history=formatted_history,
    )
    response = chat_session.send_message(message=prompt)
    return response.text


@router.post("/api/chat")
async def chat(body: ChatRequest):
    try:
        async with asyncio.timeout(CHAT_TIMEOUT_SECONDS):
            return await _chat_impl(body)
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Assistant request timed out after 35 seconds.")


async def _chat_impl(body: ChatRequest):
    try:
        message = body.message.strip()
        history = body.history

        if not message:
            raise HTTPException(status_code=400, detail="Empty message")

        snapshot = state.get_snapshot()
        index = get_rag_index()
        retrieved_contexts = []
        sources = []

        if index and index.get("chunks") and index.get("vectorizer") is not None and index.get("tfidf_matrix") is not None:
            vectorizer = index["vectorizer"]
            tfidf_matrix = index["tfidf_matrix"]
            query_vec = vectorizer.transform([message])
            similarities = np.dot(tfidf_matrix, query_vec.T).toarray().flatten()

            top_k = min(5, len(similarities))
            top_indices = np.argsort(similarities)[::-1][:top_k]

            candidates = []
            for idx in top_indices:
                score = float(similarities[idx])
                if score > 0.05:
                    chunk = index["chunks"][idx]
                    candidates.append({
                        "text": chunk["text"],
                        "file": chunk["source"],
                        "page": chunk["page"],
                        "score": round(score, 3),
                    })

            ranked = await _typesafe_call(rerank_contexts, message, candidates)
            for candidate in ranked:
                retrieved_contexts.append(candidate["text"])
                sources.append({
                    "file": candidate["file"],
                    "page": candidate["page"],
                    "score": candidate["score"],
                    **({"typesafeScore": candidate["typesafe_score"]} if "typesafe_score" in candidate else {}),
                })

        context_str = "\n\n".join([
            f"Document {i+1} (Source: {src['file']}, Page {src['page']}):\n{txt}"
            for i, (src, txt) in enumerate(zip(sources, retrieved_contexts))
        ])

        live_summary = state.get_live_dataset_summary(snapshot.df)
        reliability_summary = ml_reliability_context(body.prediction_context)

        system_instruction = (
            "You are an expert Cement Quality & Plant Operations AI Assistant. Your purpose is to help the lab technician "
            "analyze laboratory test results, explain daily/weekly/monthly strength trends, troubleshoot anomalies, "
            "interpret raw mix design concepts, and cite relevant standards.\n\n"
            f"--- 1. LIVE PLANT LABORATORY DATA & RECENT RESULTS ---\n"
            f"{live_summary}\n"
            f"----------------------------------------------------\n\n"
            f"--- 2. ML RELIABILITY & LATEST OPTIMIZER REVIEW ---\n"
            f"{reliability_summary}\n"
            f"---------------------------------------------------\n\n"
            f"--- 3. REFERENCE MANUALS & TECHNICAL STANDARDS (RAG CONTEXT) ---\n"
            f"{context_str if context_str else 'No relevant reference manual chunks retrieved.'}\n"
            f"-----------------------------------------------------------------\n\n"
            "GUIDELINES FOR ANSWERING:\n"
            "1. For questions asking about daily, weekly, monthly, or historical plant performance:\n"
            "   - ALWAYS analyze and use the LIVE PLANT LABORATORY DATA provided above.\n"
            "   - CURING RULE: Only samples with production age under 28 days can physically be 'Pending 28D Curing'. Older records without 28D strength are unrecorded tests, not in-progress curing.\n"
            "   - Calculate exact averages, compare time periods, list specific high/low dates, and report actual figures (MPa, cm²/g, %).\n"
            "2. For questions about cement chemistry, troubleshooting, standards, raw mix solver, or operational theory:\n"
            "   - Use the REFERENCE MANUALS & TECHNICAL STANDARDS and standard cement engineering principles.\n"
            "3. Be clear, precise, professional, and highlight actionable quality insights for plant engineers."
        )

        prompt = f"{system_instruction}\n\nUser Question: {message}"

        # Execute provider call with whole-request timeout of 35 seconds
        async with asyncio.timeout(35.0):
            if body.provider == "codex":
                conversation = "\n".join(
                    f"{'User' if turn.role == 'user' else 'Assistant'}: {turn.content}"
                    for turn in history
                )
                codex_prompt = (
                    f"{system_instruction}\n\n"
                    f"--- RECENT CONVERSATION ---\n{conversation or 'No earlier messages.'}\n"
                    f"---------------------------\n\nUser Question: {message}"
                )
                response_text, active_model = await ask_codex(codex_prompt)
            else:
                api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                if not api_key:
                    raise HTTPException(status_code=500, detail="Gemini API Key is not configured on the server.")

                try:
                    from google.genai import types
                except ImportError:
                    raise HTTPException(
                        status_code=500,
                        detail="google-genai package is missing. Run: pip install google-genai",
                    )

                formatted_history = [
                    types.Content(
                        role="user" if turn.role == "user" else "model",
                        parts=[types.Part.from_text(text=turn.content)],
                    )
                    for turn in history
                ]

                # Offload blocking synchronous Gemini call out of the async loop
                response_text = await anyio.to_thread.run_sync(
                    _call_gemini_sync, api_key, formatted_history, prompt
                )
                active_model = "gemini-3.8-flash"

        # Deduplicate sources
        unique_sources = []
        seen = set()
        for src in sources:
            key = (src["file"], src["page"])
            if key not in seen:
                seen.add(key)
                unique_sources.append(src)

        return {
            "response": response_text,
            "sources": unique_sources,
            "provider": body.provider,
            "model": active_model,
        }
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Assistant request timed out after 35 seconds.")
    except CodexProviderError as e:
        raise HTTPException(status_code=502, detail=f"Codex provider error: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/rag/rebuild")
async def rebuild_rag_index():
    try:
        global rag_index
        rag_index = None

        from rag_index import rebuild_index
        rebuild_index()
        return {"status": "success", "message": "RAG index rebuilt successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
