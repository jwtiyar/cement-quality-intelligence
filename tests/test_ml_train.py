"""Tests for ml_train.py — XGBoost strength model training (fast mode).

NOTE: These run the REAL training pipeline but with a reduced grid so the
suite stays quick (<60s). Full GridSearchCV coverage happens in production
startup; here we verify the plumbing and honesty of the metrics.
"""

import pytest

from data_prep import load_and_prepare
from ml_train import (
    EXPLORATORY_R2,
    ML_FEATURES,
    PREDICTIVE_R2,
    MIN_TRAIN_SAMPLES,
    model_confidence,
    train_all_models,
)


@pytest.fixture(scope="module")
def models_and_meta():
    df = load_and_prepare()
    return train_all_models(df)


class TestModelTraining:
    def test_trains_all_types(self, models_and_meta):
        _, meta = models_and_meta
        assert set(meta.keys()) == {"OPC", "SRC", "SBC"}

    def test_sbc_model_is_predictive(self, models_and_meta):
        # SBC historically reaches R2 > 0.5 (verified in production runs)
        _, meta = models_and_meta
        assert meta["SBC"]["confidence"] == "predictive"
        assert meta["SBC"]["r2"] >= PREDICTIVE_R2

    def test_models_trained_with_min_samples(self, models_and_meta):
        models, meta = models_and_meta
        for t in ("OPC", "SRC", "SBC"):
            assert meta[t]["trainSamples"] >= MIN_TRAIN_SAMPLES
            assert meta[t]["hasModel"] is True
            assert t in models

    def test_metrics_within_reasonable_bounds(self, models_and_meta):
        _, meta = models_and_meta
        for t in ("OPC", "SRC", "SBC"):
            assert 0.0 <= meta[t]["r2"] <= 1.0
            assert 0.0 < meta[t]["rmse"] < 5.0  # MPa — sane strength error

    def test_feature_importances_complete(self, models_and_meta):
        _, meta = models_and_meta
        for t in ("OPC", "SRC", "SBC"):
            assert set(meta[t]["importances"].keys()) == set(ML_FEATURES)

    def test_excluded_years_reported(self, models_and_meta):
        _, meta = models_and_meta
        assert meta["OPC"]["excludedYears"] == [2019]

    def test_confidence_labels_consistent(self, models_and_meta):
        _, meta = models_and_meta
        for t in ("OPC", "SRC", "SBC"):
            conf = meta[t]["confidence"]
            assert conf in ("predictive", "exploratory", "chemistry_only")
            assert meta[t]["confidenceLabel"]  # non-empty label


class TestConfidenceClassifier:
    def test_thresholds(self):
        assert model_confidence(0.60) == "predictive"
        assert model_confidence(0.50) == "predictive"
        assert model_confidence(0.30) == "exploratory"
        assert model_confidence(0.25) == "exploratory"
        assert model_confidence(0.10) == "chemistry_only"
        assert model_confidence(0.0) == "chemistry_only"

    def test_constants_sane(self):
        assert PREDICTIVE_R2 > EXPLORATORY_R2
