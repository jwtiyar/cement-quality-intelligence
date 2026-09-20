"""Tests for rolling, leakage-free evaluation."""

from data_prep import load_and_prepare
from ml_evaluation import rolling_evaluation


def test_rolling_evaluation_has_baselines_and_source_slices():
    report = rolling_evaluation(load_and_prepare(), "OPC", folds=2, test_size=120, bootstrap_samples=20)

    assert len(report["folds"]) == 2
    assert set(report["models"]) == {
        "train_mean", "recent_mean", "ridge", "xgboost",
        "xgboost_recent_24m", "xgboost_recency_weighted",
    }
    assert sum(report["sourceCounts"].values()) == report["rows"]
    for model in report["models"].values():
        assert set(model) == {"mae", "rmse", "r2", "bootstrap95"}
        assert model["bootstrap95"]["rmse"][0] <= model["bootstrap95"]["rmse"][1]
