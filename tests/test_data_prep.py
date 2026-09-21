"""Tests for data_prep.py — dataset loading & normalization (uses real CSV)."""

import pandas as pd
import pytest

import build_dataset
from data_prep import (
    CEMENT_TYPES,
    ML_EXCLUDED_YEARS,
    NUMERIC_COLS,
    default_csv_path,
    load_and_prepare,
    ml_training_frame,
)


@pytest.fixture(scope="module")
def df():
    return load_and_prepare()


class TestDatasetShape:
    def test_csv_exists(self):
        import os
        assert os.path.exists(default_csv_path())

    @pytest.mark.private_data
    def test_loads_rows(self, df):
        assert len(df) > 10000  # project states ~11,300 records

    def test_has_required_columns(self, df):
        for col in ["Cement_Type", "Year", "Date", "SiO2", "CaO", "Strength_28D", "Strength_28D_Source"]:
            assert col in df.columns

    def test_cement_types(self, df):
        types = set(df["Cement_Type"].unique())
        assert types == set(CEMENT_TYPES)

    @pytest.mark.private_data
    def test_year_range(self, df):
        assert df["Year"].min() == 2013
        assert df["Year"].max() == 2026

    def test_numeric_coercion(self, df):
        # All NUMERIC_COLS present in data must be float
        for col in NUMERIC_COLS:
            if col in df.columns:
                assert pd.api.types.is_float_dtype(df[col]), f"{col} not float"

    def test_7d_strength_is_not_a_model_input(self, df):
        assert "Strength_7D" not in df.columns

    def test_lsf_normalized_to_percent(self, df):
        # LSF is stored as a ratio in Excel (0.91-1.00) and must load as
        # percentage (91-100) to match the chemistry API / raw-mix solver unit.
        lsf = df["LSF"].dropna()
        assert len(lsf) > 0
        assert lsf.between(85, 110).mean() > 0.99

    def test_derives_missing_lsf_and_c3s_from_oxides(self, tmp_path):
        source = tmp_path / "minimal.csv"
        pd.DataFrame([{
            "Year": 2024,
            "Cement_Type": "OPC",
            "Date": "2024-01-01",
            "CaO": 65.0,
            "SiO2": 21.0,
            "Al2O3": 5.0,
            "Fe2O3": 3.0,
            "SO3": 2.0,
        }]).to_csv(source, index=False)

        prepared = load_and_prepare(str(source))
        expected_lsf = 100 * (65 - 0.7 * 2) / (2.8 * 21 + 1.18 * 5 + 0.65 * 3)
        expected_c3s = 4.071 * 65 - 7.6 * 21 - 6.718 * 5 - 1.43 * 3 - 2.852 * 2

        assert prepared.loc[0, "LSF"] == pytest.approx(expected_lsf)
        assert prepared.loc[0, "C3S"] == pytest.approx(expected_c3s)


def test_failed_refresh_preserves_existing_csv(tmp_path, monkeypatch):
    app_dir = tmp_path / "cement_app"
    app_dir.mkdir()
    csv_path = app_dir / "ALL_CEMENT_DATA.csv"
    csv_path.write_text("preserved\nrecord\n", encoding="utf-8")
    year_dir = tmp_path / "2024"
    year_dir.mkdir()
    (year_dir / "report.xlsx").touch()

    monkeypatch.setattr(build_dataset, "__file__", str(app_dir / "build_dataset.py"))
    monkeypatch.setattr(build_dataset.pd, "ExcelFile", lambda _: (_ for _ in ()).throw(ValueError("broken workbook")))

    with pytest.raises(RuntimeError, match="existing CSV was preserved"):
        build_dataset.extract_data()

    assert csv_path.read_text(encoding="utf-8") == "preserved\nrecord\n"


class TestStrengthNormalization:
    @pytest.mark.private_data
    def test_strength_28d_present(self, df):
        valid = df["Strength_28D"].dropna()
        assert len(valid) > 4000  # full historical target for reporting

    def test_strength_28d_source_matches_target(self, df):
        assert df.loc[df["Strength_28D"].notna(), "Strength_28D_Source"].notna().all()
        assert df.loc[df["Strength_28D"].isna(), "Strength_28D_Source"].isna().all()

    def test_strength_28d_plausible_range(self, df):
        valid = df["Strength_28D"].dropna()
        assert valid.between(20, 80).mean() > 0.95  # MPa physical range

    def test_early_strength_merged(self, df):
        # The model contract uses 2-day strength as its only early input.
        early = df[df["Strength_28D"].notna()]["Strength_Early"]
        assert early.notna().mean() > 0.5
        assert df["Strength_Early"].equals(df["Strength_2D"])
        assert "Strength_3D" not in df.columns


class TestMlTrainingFrame:
    def test_excludes_2019(self, df):
        frame = ml_training_frame(df, "OPC")
        assert not (frame["Year"] == 2019).any()

    def test_only_with_28d(self, df):
        for t in CEMENT_TYPES:
            frame = ml_training_frame(df, t)
            assert frame["Strength_28D"].notna().all()

    @pytest.mark.private_data
    def test_has_enough_samples(self, df):
        for t in CEMENT_TYPES:
            frame = ml_training_frame(df, t)
            minimum = 100 if t == "OPC" else 1000
            assert len(frame) > minimum, f"{t} too few training rows: {len(frame)}"

    def test_excluded_years_constant(self):
        assert ML_EXCLUDED_YEARS == {2019}


def test_strength_source_unification_and_provenance(tmp_path):
    source = tmp_path / "source.csv"
    pd.DataFrame([
        {"Year": 2024, "Cement_Type": "OPC", "Date": "2024-01-01", "28 day": 42.0, "28 days": 41.0},
        {"Year": 2024, "Cement_Type": "OPC", "Date": "2024-01-02", "28 day": None, "28 days": 41.0},
    ]).to_csv(source, index=False)

    prepared = load_and_prepare(str(source))

    assert prepared["Strength_28D"].tolist() == [42.0, 41.0]
    assert prepared["Strength_28D_Source"].tolist() == ["28 day", "28 days"]
    assert prepared["Strength_28D_ML"].tolist() == [42.0, 41.0]
