"""Regression checks for refresh integrity and published dataset identity."""

import os

import pandas as pd
import pytest

import build_dataset
import state
from data_prep import load_and_prepare


def _scan_with_records(tmp_path, monkeypatch, records):
    app_dir = tmp_path / "cement_app"
    app_dir.mkdir()
    year_dir = tmp_path / "2024"
    year_dir.mkdir()
    (year_dir / "daily.xlsx").touch()

    class Workbook:
        sheet_names = ["Daily Report"]

    monkeypatch.setattr(build_dataset.pd, "ExcelFile", lambda _: Workbook())
    monkeypatch.setattr(build_dataset.pd, "read_excel", lambda *args, **kwargs: pd.DataFrame(["OPC"]))
    monkeypatch.setattr(build_dataset, "parse_sheet_block", lambda *args, **kwargs: records)
    return app_dir


def _record(cao, strength=None):
    return {
        "Year": 2024,
        "Cement_Type": "OPC",
        "Date": "2024-01-01",
        "SiO2": 21.0,
        "Al2O3": 5.0,
        "Fe2O3": 3.0,
        "CaO": cao,
        "28 day": strength,
    }


def test_refresh_rejects_multiple_year_workbooks(tmp_path):
    app_dir = tmp_path / "cement_app"
    app_dir.mkdir()
    year_dir = tmp_path / "2024"
    year_dir.mkdir()
    (year_dir / "a.xlsx").touch()
    (year_dir / "b.xlsx").touch()

    with pytest.raises(RuntimeError, match="Multiple.*2024"):
        build_dataset.extract_data(base_dir=str(app_dir), target_path=str(tmp_path / "candidate.csv"))

    assert not (tmp_path / "candidate.csv").exists()


@pytest.mark.parametrize(
    ("old_rows", "new_rows"),
    [
        ([_record(65.0)], [_record(64.0)]),
        ([_record(65.0), _record(66.0)], [_record(65.0)]),
        ([_record(65.0, 45.0)], [_record(65.0, None)]),
    ],
)
def test_refresh_rejects_lost_or_changed_existing_measurements(tmp_path, monkeypatch, old_rows, new_rows):
    app_dir = _scan_with_records(tmp_path, monkeypatch, new_rows)
    active = app_dir / "ALL_CEMENT_DATA.csv"
    pd.DataFrame(old_rows).to_csv(active, index=False)
    before = active.read_bytes()

    with pytest.raises(build_dataset.UnexplainedDataLossError):
        build_dataset.extract_data(base_dir=str(app_dir), existing_csv_path=str(active))

    assert active.read_bytes() == before


def test_refresh_accepts_new_result_for_previously_empty_measurement(tmp_path, monkeypatch):
    app_dir = _scan_with_records(tmp_path, monkeypatch, [_record(65.0, 45.0)])
    active = app_dir / "ALL_CEMENT_DATA.csv"
    pd.DataFrame([_record(65.0, None)]).to_csv(active, index=False)
    candidate = tmp_path / "candidate.csv"

    result = build_dataset.extract_data(
        base_dir=str(app_dir), target_path=str(candidate), existing_csv_path=str(active)
    )

    assert result.loc[0, "28 day"] == 45.0
    assert pd.read_csv(candidate).loc[0, "28 day"] == 45.0


def test_refresh_rejects_disappearing_measurement_column(tmp_path, monkeypatch):
    new_row = _record(65.0)
    del new_row["28 day"]
    app_dir = _scan_with_records(tmp_path, monkeypatch, [new_row])
    active = app_dir / "ALL_CEMENT_DATA.csv"
    pd.DataFrame([_record(65.0, 45.0)]).to_csv(active, index=False)

    with pytest.raises(build_dataset.UnexplainedDataLossError, match="28 day"):
        build_dataset.extract_data(base_dir=str(app_dir), existing_csv_path=str(active))


def test_explicit_override_accepts_reviewed_historical_correction(tmp_path, monkeypatch):
    app_dir = _scan_with_records(tmp_path, monkeypatch, [_record(64.0)])
    active = app_dir / "ALL_CEMENT_DATA.csv"
    pd.DataFrame([_record(65.0)]).to_csv(active, index=False)

    result = build_dataset.extract_data(
        base_dir=str(app_dir), existing_csv_path=str(active), allow_deletions=True
    )

    assert result.loc[0, "CaO"] == 64.0


def test_refresh_does_not_replace_an_unreadable_active_dataset(tmp_path, monkeypatch):
    app_dir = _scan_with_records(tmp_path, monkeypatch, [_record(65.0)])
    active = app_dir / "ALL_CEMENT_DATA.csv"
    active.write_bytes(b"not,a,cement,dataset\n1,2,3,4\n")
    before = active.read_bytes()

    with pytest.raises(RuntimeError, match="could not validate existing CSV"):
        build_dataset.extract_data(base_dir=str(app_dir), existing_csv_path=str(active))

    assert active.read_bytes() == before


def test_dataset_version_changes_when_csv_values_change_but_dates_and_mtime_do_not(tmp_path, synthetic_csv_path):
    original = pd.read_csv(synthetic_csv_path).head(12)
    changed = original.copy()
    changed.loc[0, "CaO"] += 0.5
    paths = [tmp_path / "original.csv", tmp_path / "changed.csv"]
    for frame, path in zip((original, changed), paths):
        frame.to_csv(path, index=False)
        os.utime(path, (1_700_000_000, 1_700_000_000))

    snapshots = [
        state._build_cache_and_snapshot(load_and_prepare(str(path)), str(path), {}, {}, {"status": "idle"})
        for path in paths
    ]

    assert snapshots[0].dataset_version != snapshots[1].dataset_version
