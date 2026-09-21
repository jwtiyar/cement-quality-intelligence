"""Tests for rolling, leakage-free evaluation."""

from data_prep import load_and_prepare
from ml_evaluation import rolling_evaluation


def test_rolling_evaluation_has_baselines_and_source_slices():
    report = rolling_evaluation(load_and_prepare(), "SRC", folds=2, test_size=120, bootstrap_samples=20)

    assert len(report["folds"]) == 2
    assert set(report["models"]) == {
        "train_mean", "recent_mean", "ridge", "xgboost",
        "xgboost_recent_24m", "xgboost_recency_weighted",
    }
    assert sum(report["sourceCounts"].values()) == report["rows"]
    for model in report["models"].values():
        assert set(model) == {"mae", "rmse", "r2", "bootstrap95"}
        assert model["bootstrap95"]["rmse"][0] <= model["bootstrap95"]["rmse"][1]


def test_rolling_evaluation_synthetic_fixture_multi_fold(synthetic_csv_path):
    df = load_and_prepare(synthetic_csv_path)
    report = rolling_evaluation(df, "OPC", folds=3, test_size=20, bootstrap_samples=10)

    assert report["status"] == "evaluated"
    assert len(report["folds"]) == 3
    assert "promotionDecision" in report
    assert isinstance(report["promotionDecision"]["promoted"], bool)


def test_rolling_evaluation_sparse_fixture_insufficient_evidence(sparse_csv_path):
    df = load_and_prepare(sparse_csv_path)
    report = rolling_evaluation(df, "OPC", folds=3, test_size=20)

    assert report["status"] == "insufficient_evidence"
    assert report["promotionDecision"]["promoted"] is False
    assert "insufficient" in report["promotionDecision"]["reason"].lower()
