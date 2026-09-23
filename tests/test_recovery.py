"""Tests for crash recovery, transactional refresh, timeout cancellation, RAG freshness, and insufficient evidence."""

import asyncio
import hashlib
import os
import shutil
import time
import pandas as pd
import pytest
from fastapi import FastAPI
import httpx

import state
from data_prep import load_and_prepare
from ml_train import train_all_models
from rag_index import rebuild_index
from routes import get_rag_index, reload_rag_index, router
from tests.conftest import SYNTHETIC_CSV_PATH, SPARSE_CSV_PATH


@pytest.fixture(autouse=True)
def isolate_assistant_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


class TestCrashRecovery:
    def test_missing_csv_restores_from_backup(self, tmp_path):
        active_csv = str(tmp_path / "data.csv")
        bak_csv = active_csv + ".bak"

        # Create valid backup
        shutil.copyfile(SYNTHETIC_CSV_PATH, bak_csv)
        assert not os.path.exists(active_csv)

        state.reload_from_csv(active_csv)

        assert os.path.exists(active_csv)
        assert os.path.getsize(active_csv) > 0
        df = load_and_prepare(active_csv)
        assert len(df) == 360

    def test_empty_csv_restores_from_backup(self, tmp_path):
        active_csv = str(tmp_path / "data.csv")
        bak_csv = active_csv + ".bak"

        # Create 0-byte file and valid backup
        with open(active_csv, "w") as f:
            pass
        assert os.path.getsize(active_csv) == 0

        shutil.copyfile(SYNTHETIC_CSV_PATH, bak_csv)
        state.reload_from_csv(active_csv)

        assert os.path.getsize(active_csv) > 0
        df = load_and_prepare(active_csv)
        assert len(df) == 360

    def test_corrupt_csv_restores_from_backup(self, tmp_path):
        active_csv = str(tmp_path / "data.csv")
        bak_csv = active_csv + ".bak"

        # Create corrupt/malformed file and valid backup
        with open(active_csv, "w", encoding="utf-8") as f:
            f.write("GARBAGE HEADER WITH NO VALID COLUMNS\n\x00\xff\xfe random binary junk\n")

        shutil.copyfile(SYNTHETIC_CSV_PATH, bak_csv)
        state.reload_from_csv(active_csv)

        assert os.path.exists(active_csv)
        df = load_and_prepare(active_csv)
        assert len(df) == 360


class TestTransactionalRefreshAndTimeout:
    def test_successful_refresh_publishes_the_committed_csv_version(self, tmp_path, monkeypatch):
        active_csv = str(tmp_path / "ALL_CEMENT_DATA.csv")
        shutil.copyfile(SYNTHETIC_CSV_PATH, active_csv)
        monkeypatch.setenv("CEMENT_DATA_CSV", active_csv)
        state.reload_from_csv(active_csv)
        old_version = state.get_snapshot().dataset_version

        def stage(staging_csv, allow_deletions, active_path):
            candidate = pd.read_csv(SYNTHETIC_CSV_PATH)
            candidate.loc[0, "CaO"] += 0.5
            candidate.to_csv(staging_csv, index=False)
            return load_and_prepare(staging_csv), {}, {}

        monkeypatch.setattr(state, "_stage_refresh_sync", stage)
        published = asyncio.run(state.refresh_dataset_transactional())

        with open(active_csv, "rb") as csv_file:
            committed_version = hashlib.file_digest(csv_file, "sha256").hexdigest()[:12]
        assert committed_version != old_version
        assert published.dataset_version == committed_version
        assert state.get_snapshot().data_cache["dataset"]["version"] == committed_version

    def test_worker_finishing_after_timeout_cannot_commit(self, tmp_path, monkeypatch):
        """Worker running in threadpool finishing after request timeout must NOT commit."""
        async def _run():
            active_csv = str(tmp_path / "ALL_CEMENT_DATA.csv")
            shutil.copyfile(SYNTHETIC_CSV_PATH, active_csv)
            monkeypatch.setenv("CEMENT_DATA_CSV", active_csv)

            # Initialize state with original synthetic data
            state.reload_from_csv(active_csv)
            initial_snapshot = state.get_snapshot()
            initial_version = initial_snapshot.dataset_version
            initial_mtime = os.path.getmtime(active_csv)

            worker_finished = False

            def delayed_staging(staging_csv, allow_deletions, active_path):
                nonlocal worker_finished
                time.sleep(0.3)
                df_mod = pd.read_csv(SYNTHETIC_CSV_PATH).head(50)
                df_mod.to_csv(staging_csv, index=False)
                df_new = load_and_prepare(staging_csv)
                models_new, ml_data_new = train_all_models(df_new)
                worker_finished = True
                return df_new, models_new, ml_data_new

            monkeypatch.setattr(state, "_stage_refresh_sync", delayed_staging)

            # Call refresh with an aggressive timeout of 0.05s
            with pytest.raises((TimeoutError, asyncio.CancelledError)):
                async with asyncio.timeout(0.05):
                    await state.refresh_dataset_transactional()

            # Wait for the background worker thread to finish its delayed staging work
            await asyncio.sleep(0.4)
            assert worker_finished is True

            # Verify that the delayed worker finishing NEVER committed to active_csv or published state!
            assert os.path.getmtime(active_csv) == initial_mtime
            assert state.get_snapshot().dataset_version == initial_version
            assert len(state.get_snapshot().df) == len(initial_snapshot.df)
            assert not list(tmp_path.glob("*.staging.*"))

        asyncio.run(_run())

    def test_post_replace_failure_rolls_back_disk_to_backup(self, tmp_path, monkeypatch):
        active_csv = str(tmp_path / "ALL_CEMENT_DATA.csv")
        shutil.copyfile(SYNTHETIC_CSV_PATH, active_csv)
        monkeypatch.setenv("CEMENT_DATA_CSV", active_csv)

        state.reload_from_csv(active_csv)
        original_snapshot = state.get_snapshot()
        original_summary = (tmp_path / "knowledge_base/latest_daily_results.txt").read_bytes()
        rebuild_index()
        index_path = tmp_path / "knowledge_base/rag_index.pkl"
        original_index = index_path.read_bytes()

        async def _run():
            # Mock rebuild_index to fail AFTER os.replace has occurred
            def broken_rebuild():
                index_path.write_bytes(b"incomplete candidate index")
                raise RuntimeError("Simulated RAG rebuild catastrophic failure")

            monkeypatch.setattr("rag_index.rebuild_index", broken_rebuild)

            # Staging worker produces a distinct 10-row dataset
            def custom_staging(staging_csv, allow_deletions, active_path):
                df_mod = pd.read_csv(SYNTHETIC_CSV_PATH).head(10)
                df_mod.to_csv(staging_csv, index=False)
                df_new = load_and_prepare(staging_csv)
                return df_new, {}, {}

            monkeypatch.setattr(state, "_stage_refresh_sync", custom_staging)

            with pytest.raises(RuntimeError, match="Simulated RAG rebuild"):
                await asyncio.wait_for(state.refresh_dataset_transactional(), timeout=5)

            # Verify active_csv was rolled back to original 360 rows from .bak
            df_active = load_and_prepare(active_csv)
            assert len(df_active) == 360
            # Active snapshot was preserved
            assert state.get_snapshot().dataset_version == original_snapshot.dataset_version
            assert (tmp_path / "knowledge_base/latest_daily_results.txt").read_bytes() == original_summary
            assert index_path.read_bytes() == original_index

        asyncio.run(_run())


class TestAssistantFreshnessAndRag:
    def test_actual_assistant_summary_file_rebuilt_and_retrieved(self, tmp_path, monkeypatch):
        """Verify knowledge_base/latest_daily_results.txt rebuilds RAG and chat retrieves new version."""
        kb_dir = tmp_path / "knowledge_base"
        kb_dir.mkdir()
        summary_file = kb_dir / "latest_daily_results.txt"
        rag_index_path = kb_dir / "rag_index.pkl"

        # Unique marker string to verify retrieval freshness
        unique_marker = f"PLANT_ALERT_RECORD_TEST_{int(time.time())}"
        summary_file.write_text(
            f"=== LIVE PLANT LABORATORY DATASET SUMMARY ===\nSpecial notice: {unique_marker} recorded on kiln line 2.\n",
            encoding="utf-8",
        )

        monkeypatch.setattr("rag_index.KNOWLEDGE_DIR", str(kb_dir))
        monkeypatch.setattr("rag_index.INDEX_PATH", str(rag_index_path))
        monkeypatch.setenv("RAG_INDEX_PATH", str(rag_index_path))

        # Rebuild index from latest_daily_results.txt and reload
        rebuild_index()
        assert os.path.exists(rag_index_path)

        def unexpected_rebuild():
            raise AssertionError("Reload must use the committed index, not rebuild it")

        monkeypatch.setattr("rag_index.rebuild_index", unexpected_rebuild)
        idx = reload_rag_index()
        assert idx is not None
        assert any(unique_marker in c["text"] for c in idx["chunks"])


class TestInsufficientEvidenceMetrics:
    def test_insufficient_evidence_does_not_report_zero_rmse(self):
        """When samples are too few to validate baseline error, return unavailable (None) metrics, not 0.0."""
        sparse_df = load_and_prepare(SPARSE_CSV_PATH)
        models, meta = train_all_models(sparse_df)

        for c_type in ("OPC", "SRC", "SBC"):
            c_meta = meta[c_type]
            assert c_meta["confidence"] == "insufficient_evidence"
            assert c_meta["r2"] is None
            assert c_meta["rmse"] is None
            assert c_meta["hasModel"] is False
            assert c_meta["modelBeatsRecentBaseline"] is False

    def test_curing_status_strictly_uses_today(self):
        """Samples produced >= 28 days ago from today must be marked 'Not recorded / missing', NEVER 'Pending'."""
        today = pd.Timestamp.now().normalize()
        past_date = (today - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
        recent_date = (today - pd.Timedelta(days=5)).strftime("%Y-%m-%d")

        df = pd.DataFrame([
            {
                "Year": 2024,
                "Cement_Type": "OPC",
                "Date": past_date,
                "Date_str": past_date,
                "Date_dt": pd.to_datetime(past_date),
                "Strength_28D": None,
                "Strength_Early": 25.0,
                "Fineness": 3200,
                "LSF": 95.0,
                "C3S": 55.0,
                "CaO": 64.0,
                "SO3": 2.2,
                "Strength_28D_Source": "unknown",
            },
            {
                "Year": 2026,
                "Cement_Type": "OPC",
                "Date": recent_date,
                "Date_str": recent_date,
                "Date_dt": pd.to_datetime(recent_date),
                "Strength_28D": None,
                "Strength_Early": 24.0,
                "Fineness": 3250,
                "LSF": 96.0,
                "C3S": 56.0,
                "CaO": 64.5,
                "SO3": 2.3,
                "Strength_28D_Source": "unknown",
            },
        ])

        summary = state.get_live_dataset_summary(df)
        assert f"Date: {past_date} | Type: OPC | 28D Strength: Not recorded / missing" in summary
        assert f"Date: {recent_date} | Type: OPC | 28D Strength: Pending 28D Curing" in summary
