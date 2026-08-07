"""Tests for data_prep.py — dataset loading & normalization (uses real CSV)."""

import pandas as pd
import pytest

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

    def test_loads_rows(self, df):
        assert len(df) > 10000  # project states ~11,300 records

    def test_has_required_columns(self, df):
        for col in ["Cement_Type", "Year", "Date", "SiO2", "CaO", "Strength_28D"]:
            assert col in df.columns

    def test_cement_types(self, df):
        types = set(df["Cement_Type"].unique())
        assert types == set(CEMENT_TYPES)

    def test_year_range(self, df):
        assert df["Year"].min() == 2013
        assert df["Year"].max() == 2026

    def test_numeric_coercion(self, df):
        # All NUMERIC_COLS present in data must be float
        for col in NUMERIC_COLS:
            if col in df.columns:
                assert pd.api.types.is_float_dtype(df[col]), f"{col} not float"

    def test_lsf_normalized_to_percent(self, df):
        # LSF is stored as a ratio in Excel (0.91-1.00) and must load as
        # percentage (91-100) to match the chemistry API / raw-mix solver unit.
        lsf = df["LSF"].dropna()
        assert len(lsf) > 0
        assert lsf.between(85, 110).mean() > 0.99


class TestStrengthNormalization:
    def test_strength_28d_present(self, df):
        valid = df["Strength_28D"].dropna()
        assert len(valid) > 4000  # README: ~5,000 of ~11,500

    def test_strength_28d_plausible_range(self, df):
        valid = df["Strength_28D"].dropna()
        assert valid.between(20, 80).mean() > 0.95  # MPa physical range

    def test_early_strength_merged(self, df):
        # Either 2D or 3D must feed Strength_Early where 28D exists
        early = df[df["Strength_28D"].notna()]["Strength_Early"]
        assert early.notna().mean() > 0.5


class TestMlTrainingFrame:
    def test_excludes_2019(self, df):
        frame = ml_training_frame(df, "OPC")
        assert not (frame["Year"] == 2019).any()

    def test_only_with_28d(self, df):
        for t in CEMENT_TYPES:
            frame = ml_training_frame(df, t)
            assert frame["Strength_28D"].notna().all()

    def test_has_enough_samples(self, df):
        for t in CEMENT_TYPES:
            frame = ml_training_frame(df, t)
            assert len(frame) > 1000, f"{t} too few training rows: {len(frame)}"

    def test_excluded_years_constant(self):
        assert ML_EXCLUDED_YEARS == {2019}
