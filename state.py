"""Application state: immutable snapshots, crash recovery, atomic refresh lock, and API cache.

Single-worker deployment (uvicorn --workers 1) is required for multi-process safety.
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import os
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import anyio

import numpy as np
import pandas as pd

from data_prep import CEMENT_TYPES, default_csv_path, load_and_prepare
from ml_train import ML_FEATURES, train_all_models

ANOMALY_BOUNDS = {
    "SiO2": (17, 26),
    "Al2O3": (2, 8),
    "Fe2O3": (1, 6),
    "CaO": (55, 70),
    "MgO": (0, 6),
    "SO3": (0.5, 4.5),
    "Strength_28D": (20, 80),
    "Fineness": (2000, 6000),
    "C3S": (30, 80),
    "C3A": (0, 15),
}


@dataclass(frozen=True)
class AppStateSnapshot:
    """Immutable view of active dataset, models, and cache for request isolation."""
    df: pd.DataFrame
    xgb_models: dict[str, Any]
    data_cache: dict[str, Any]
    dataset_version: str
    refresh_meta: dict[str, Any]
    created_at: str


_current_snapshot: AppStateSnapshot | None = None
_refresh_lock = asyncio.Lock()

# Module-level variables maintained for backward-compatibility with existing callers
data_cache: dict[str, Any] = {}
xgb_models: dict[str, Any] = {}
df_global: pd.DataFrame | None = None


def get_snapshot() -> AppStateSnapshot:
    """Return the currently published state snapshot, ensuring request-level consistency."""
    global _current_snapshot
    if _current_snapshot is None:
        reload_from_csv()
    if _current_snapshot is None:
        raise RuntimeError("Application state failed to initialize.")
    return _current_snapshot


def _chart_series(series: pd.Series) -> list[float | None]:
    return [None if pd.isna(v) else float(v) for v in series]


def _find_latest_month(df: pd.DataFrame) -> dict[str, int | None]:
    valid = df.dropna(subset=["Date_dt"])
    if valid.empty:
        return {"year": None, "month": None}
    latest = valid["Date_dt"].max()
    return {"year": int(latest.year), "month": int(latest.month)}


def _find_28d_era_start(df: pd.DataFrame) -> int | None:
    for year in sorted(df["Year"].unique()):
        yr_df = df[df["Year"] == year]
        if yr_df.empty:
            continue
        ratio = yr_df["Strength_28D"].notna().mean()
        if ratio >= 0.5:
            return int(year)
    return None


def get_live_dataset_summary(df: pd.DataFrame | None = None) -> str:
    """Return an exact, Python-calculated summary of laboratory data for assistant context."""
    if df is None:
        snapshot = _current_snapshot
        df = snapshot.df if snapshot is not None else df_global
    if df is None or df.empty:
        return "No live laboratory dataset loaded."

    valid_df = df.dropna(subset=["Date_dt"]).sort_values("Date_dt", ascending=False)
    if valid_df.empty:
        return "No dated laboratory records found."

    earliest = valid_df["Date_dt"].min().strftime("%Y-%m-%d")
    latest = valid_df["Date_dt"].max().strftime("%Y-%m-%d")
    latest_dt = valid_df["Date_dt"].max()
    total_records = len(df)

    lines = []
    lines.append("=== LIVE PLANT LABORATORY DATASET SUMMARY (EXACT PYTHON STATISTICS) ===")
    lines.append(f"Total Daily Laboratory Records: {total_records}")
    lines.append(f"Data Coverage Range: {earliest} to {latest} (Latest Date: {latest})")

    lines.append("\n--- OVERALL HISTORICAL AVERAGES PER CEMENT TYPE ---")
    for ctype in sorted(df["Cement_Type"].unique()):
        sub = df[df["Cement_Type"] == ctype]
        s28_avg = sub["Strength_28D"].mean()
        se_avg = sub["Strength_Early"].mean()
        fin_avg = sub["Fineness"].mean()
        lsf_avg = sub["LSF"].mean()
        c3s_avg = sub["C3S"].mean()

        lines.append(
            f"• [{ctype}] ({len(sub)} tests): 28D Strength Avg={s28_avg:.1f} MPa | "
            f"Early Strength Avg={se_avg:.1f} MPa | Blaine Avg={fin_avg:.0f} cm²/g | "
            f"LSF Avg={lsf_avg:.1f}% | C3S Avg={c3s_avg:.1f}%"
        )

    # Monthly Summary (Last 24 months)
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
            lsf_str = f"LSF={lsf_vals.mean():.1f}%" if not lsf_vals.empty else "N/A"

            lines.append(
                f"• {ym} | {ctype} ({len(sub)} records) -> 28D Strength: {s28_str} | "
                f"Early Strength: {se_str} | Blaine: {fin_str} | {lsf_str}"
            )

    today = pd.Timestamp.now().normalize()
    lines.append("\n--- LATEST DAILY LABORATORY TEST RESULTS (MOST RECENT 60 TEST DAYS) ---")
    lines.append("(Note: Only samples produced within the last 28 days from today can physically be 'Pending 28D Curing'. Older missing tests are unrecorded.)")
    recent_60 = valid_df.head(60)
    for _, row in recent_60.iterrows():
        d_str = str(row["Date_str"])
        ctype = row["Cement_Type"]
        sample_dt = row.get("Date_dt")
        sample_date = pd.to_datetime(sample_dt).normalize() if pd.notna(sample_dt) else None
        age_days = (today - sample_date).days if sample_date is not None else 999

        s28_raw = row.get("Strength_28D")
        if pd.notna(s28_raw):
            s28 = f"{s28_raw:.1f} MPa"
        elif age_days < 28:
            s28 = "Pending 28D Curing"
        else:
            s28 = "Not recorded / missing"

        se_raw = row.get("Strength_Early")
        if pd.notna(se_raw):
            se = f"{se_raw:.1f} MPa"
        elif age_days < 2:
            se = "Pending Early Curing"
        else:
            se = "Not recorded / missing"

        fin = f"{row['Fineness']:.0f} cm²/g" if pd.notna(row.get("Fineness")) else "N/A"
        lsf_raw = row.get("LSF")
        lsf_str = f"{lsf_raw:.1f}%" if pd.notna(lsf_raw) else "N/A"
        c3s = f"{row.get('C3S', 0):.1f}%" if pd.notna(row.get("C3S")) else "N/A"
        cao = f"{row.get('CaO', 0):.1f}%" if pd.notna(row.get("CaO")) else "N/A"
        so3 = f"{row.get('SO3', 0):.2f}%" if pd.notna(row.get("SO3")) else "N/A"

        lines.append(
            f"Date: {d_str} | Type: {ctype} | 28D Strength: {s28} | Early Strength: {se} | "
            f"Blaine: {fin} | LSF: {lsf_str} | C3S: {c3s} | CaO: {cao} | SO3: {so3}"
        )

    return "\n".join(lines)


def write_dataset_summary_to_file(df: pd.DataFrame) -> None:
    """Generate and write a clean text summary of laboratory results into knowledge_base."""
    os.makedirs("knowledge_base", exist_ok=True)
    summary_path = os.path.join("knowledge_base", "latest_daily_results.txt")
    summary_text = get_live_dataset_summary(df)
    tmp_path = summary_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(summary_text)
    os.replace(tmp_path, summary_path)


def _build_cache_and_snapshot(
    df: pd.DataFrame,
    csv_path: str,
    models: dict[str, Any],
    ml_data: dict[str, Any],
    refresh_meta: dict[str, Any],
) -> AppStateSnapshot:
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
    if os.path.exists(csv_path):
        csv_mtime = datetime.fromtimestamp(os.path.getmtime(csv_path), tz=timezone.utc).isoformat()

    strength_28_count = int(df["Strength_28D"].notna().sum())

    anomalies = []
    for param, (low, high) in ANOMALY_BOUNDS.items():
        if param in df.columns:
            s_numeric = pd.to_numeric(df[param], errors="coerce")
            mask = s_numeric.notna() & ((s_numeric < low) | (s_numeric > high))
            outliers = df[mask]
            for _, row in outliers.iterrows():
                anomalies.append({
                    "Date": str(row["Date_str"]),
                    "Type": str(row.get("Cement_Type", "Unknown")),
                    "Parameter": param,
                    "Value": round(float(row[param]), 2),
                    "Expected": f"{low} - {high}",
                })

    latest_rec_date = str(df["Date_str"].dropna().max()) if "Date_str" in df.columns and not df["Date_str"].dropna().empty else None

    with open(csv_path, "rb") as csv_file:
        dataset_version = hashlib.file_digest(csv_file, "sha256").hexdigest()[:12]

    cache = {
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
            "latestRecordDate": latest_rec_date,
            "version": dataset_version,
            "retrainPolicy": "Models retrained in memory on startup and validated refresh",
            "mlExcludedYears": sorted({2019}),
            "freshness": {
                "latestRecordDate": latest_rec_date,
                "datasetVersion": dataset_version,
                "refreshStatus": refresh_meta.get("status", "idle"),
                "refreshTimestamp": refresh_meta.get("timestamp"),
                "refreshError": refresh_meta.get("error"),
            },
            "strength28Note": (
                "Consolidated IQS 5 / EN 196-1 28-day strength ({n} records).".format(n=strength_28_count)
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
        "refreshStatus": refresh_meta,
    }

    return AppStateSnapshot(
        df=df,
        xgb_models=models,
        data_cache=cache,
        dataset_version=dataset_version,
        refresh_meta=refresh_meta,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def reload_from_csv(csv_path: str | None = None) -> None:
    """
    Startup loader with crash recovery.
    Decoupled: if ML training fails during cold startup, solver and data browsing remain online.
    """
    global _current_snapshot, data_cache, xgb_models, df_global

    path = csv_path or default_csv_path()

    # Crash recovery: if primary CSV is missing or empty, attempt restore from .bak
    if (not os.path.exists(path) or os.path.getsize(path) == 0) and os.path.exists(path + ".bak"):
        print(f"Warning: Primary CSV '{path}' missing or empty; attempting restore from backup...")
        try:
            shutil.copyfile(path + ".bak", path)
            print(f"Restored primary dataset from backup: {path}.bak")
        except Exception as e:
            print(f"Failed to restore from backup: {e}")

    print("Loading and cleaning dataset...")
    try:
        df = load_and_prepare(path)
    except Exception as e:
        if os.path.exists(path + ".bak"):
            print(f"Warning: Primary CSV '{path}' corrupted or failed to load ({e}); attempting restore from backup...")
            try:
                shutil.copyfile(path + ".bak", path)
                df = load_and_prepare(path)
                print(f"Restored primary dataset from backup after corruption: {path}.bak")
            except Exception as e2:
                print(f"Failed to restore from backup after corruption: {e2}")
                raise e2 from e
        else:
            raise

    # Cold startup ML training resilience: failures in ML do not take down the server
    models: dict[str, Any] = {}
    ml_data: dict[str, Any] = {}
    try:
        models, ml_data = train_all_models(df)
    except Exception as e:
        print(f"Warning: ML model training failed during startup: {e}. Solver remains available.")
        for c in CEMENT_TYPES:
            ml_data[c] = {
                "confidence": "insufficient_evidence",
                "confidenceLabel": "ML unavailable (startup training error)",
                "hasModel": False,
                "r2": None,
                "rmse": None,
                "averages": {feat: float(df[feat].mean()) if feat in df.columns else 0.0 for feat in ML_FEATURES},
            }

    try:
        write_dataset_summary_to_file(df)
    except Exception as e:
        print(f"Error saving dataset text summary: {e}")

    snapshot = _build_cache_and_snapshot(
        df=df,
        csv_path=path,
        models=models,
        ml_data=ml_data,
        refresh_meta={
            "status": "idle",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": None,
        },
    )

    _current_snapshot = snapshot
    df_global = snapshot.df
    xgb_models = snapshot.xgb_models
    data_cache = snapshot.data_cache
    print(f"State initialized: {len(df)} records, version {snapshot.dataset_version}")


def _stage_refresh_sync(
    staging_csv: str,
    allow_deletions: bool,
    active_csv: str | None,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    """Synchronous worker that performs extraction and training purely in staging.

    Runs in a worker thread and strictly does NOT touch active_csv, .bak, or global state.
    """
    from build_dataset import extract_data

    extract_data(
        target_path=staging_csv,
        allow_deletions=allow_deletions,
        existing_csv_path=active_csv if (active_csv and os.path.exists(active_csv)) else None,
    )
    df_new = load_and_prepare(staging_csv)
    models_new, ml_data_new = train_all_models(df_new)
    return df_new, models_new, ml_data_new


async def refresh_dataset_transactional(
    allow_deletions: bool = False,
    cancellation_check: Callable[[], bool] | None = None,
) -> AppStateSnapshot:
    """
    Transactional refresh:
    Worker thread extracts and trains purely in staging.
    On the request side, verify deadline/cancellation, preserve recoverable .bak,
    atomically swap files and snapshot, and rebuild RAG index from latest_daily_results.txt.
    If any step fails, disk rolls back to .bak and previous snapshot is preserved.
    """
    global _current_snapshot, data_cache, xgb_models, df_global

    import rag_index

    active_csv = default_csv_path()
    refresh_token = hashlib.sha256(f"{datetime.now(timezone.utc).isoformat()}:{os.getpid()}".encode()).hexdigest()[:8]
    staging_csv = f"{active_csv}.staging.{refresh_token}"
    bak_csv = active_csv + ".bak"

    async with _refresh_lock:
        committed = False
        abandoned = threading.Event()
        auxiliary_backups: dict[str, str | None] = {}
        stage_task: asyncio.Task | None = None

        def stage():
            try:
                return _stage_refresh_sync(staging_csv, allow_deletions, active_csv)
            finally:
                if abandoned.is_set() and os.path.exists(staging_csv):
                    os.remove(staging_csv)

        try:
            # 1. Staging extraction and training on background worker thread
            stage_task = asyncio.create_task(anyio.to_thread.run_sync(stage, abandon_on_cancel=True))
            # This host can miss a worker-thread wakeup; the bounded wait keeps refresh responsive.
            while not stage_task.done():
                await asyncio.wait({stage_task}, timeout=0.25)
            df_new, models_new, ml_data_new = stage_task.result()

            # 2. Check for caller timeout/cancellation before commit
            if cancellation_check and cancellation_check():
                if os.path.exists(staging_csv):
                    try:
                        os.remove(staging_csv)
                    except Exception:
                        pass
                raise asyncio.CancelledError("Refresh operation timed out before commit step.")

            # 3. Pre-build candidate snapshot in memory before touching disk
            refresh_meta = {
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": None,
                "records": len(df_new),
            }
            candidate_snapshot = _build_cache_and_snapshot(
                df=df_new,
                csv_path=staging_csv,
                models=models_new,
                ml_data=ml_data_new,
                refresh_meta=refresh_meta,
            )

            # Keep the assistant's published files paired with the active CSV.
            for path in ("knowledge_base/latest_daily_results.txt", rag_index.INDEX_PATH):
                backup = f"{path}.refresh.{refresh_token}.bak" if os.path.isfile(path) else None
                if backup:
                    shutil.copyfile(path, backup)
                auxiliary_backups[path] = backup

            # 4. Safe backup preservation
            if os.path.exists(active_csv):
                shutil.copyfile(active_csv, bak_csv)

            # 5. Atomic file replacement
            os.replace(staging_csv, active_csv)
            committed = True

            # 6. Synchronize text summary and RAG index from latest_daily_results.txt
            write_dataset_summary_to_file(df_new)
            rag_index.rebuild_index()

            # 7. Atomic in-memory snapshot publication
            _current_snapshot = candidate_snapshot
            df_global = candidate_snapshot.df
            xgb_models = candidate_snapshot.xgb_models
            data_cache = candidate_snapshot.data_cache

            print(f"Refresh completed successfully: {len(df_new)} records, version {candidate_snapshot.dataset_version}")
            return candidate_snapshot

        except (Exception, asyncio.CancelledError, BaseException) as e:
            abandoned.set()
            if stage_task is not None and not stage_task.done():
                stage_task.cancel()
            # If disk was replaced, but summary/RAG/snapshot publication failed,
            # roll back active_csv from bak_csv immediately.
            if committed and os.path.exists(bak_csv):
                try:
                    shutil.copyfile(bak_csv, active_csv)
                    print(f"Rolled back active CSV from {bak_csv} due to post-replace failure: {e}")
                except Exception as rb_err:
                    print(f"CRITICAL: Failed to roll back active CSV from backup: {rb_err}")
            if committed:
                for path, backup in auxiliary_backups.items():
                    try:
                        if backup:
                            os.replace(backup, path)
                        elif os.path.exists(path):
                            os.remove(path)
                    except Exception as rb_err:
                        print(f"CRITICAL: Failed to roll back {path}: {rb_err}")

            # Clean up temporary staging file on failure
            if os.path.exists(staging_csv):
                try:
                    os.remove(staging_csv)
                except Exception:
                    pass

            # Record failure status in existing snapshot metadata without losing active state
            if _current_snapshot is not None:
                updated_meta = {
                    "status": "failed",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": str(e),
                }
                _current_snapshot = AppStateSnapshot(
                    df=_current_snapshot.df,
                    xgb_models=_current_snapshot.xgb_models,
                    data_cache={**_current_snapshot.data_cache, "refreshStatus": updated_meta},
                    dataset_version=_current_snapshot.dataset_version,
                    refresh_meta=updated_meta,
                    created_at=_current_snapshot.created_at,
                )
                data_cache = _current_snapshot.data_cache
            raise
        finally:
            for backup in auxiliary_backups.values():
                if backup and os.path.exists(backup):
                    try:
                        os.remove(backup)
                    except OSError as cleanup_err:
                        print(f"Warning: Could not remove refresh backup {backup}: {cleanup_err}")
