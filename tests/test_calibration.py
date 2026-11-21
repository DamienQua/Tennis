"""Calibration uses a temporal holdout and the exact production coefficients."""

import json
import numpy as np
import pandas as pd
import pytest

from analysis.probability_model import BASELINE_WEIGHTS, get_weights, load_model
from backtest.calibrate_weights import calibrate_from_dataframe


def archive_rows():
    return pd.DataFrame([
        {"Date": date, "Tournament": "Test", "Surface": "Clay", "Comment": "Completed",
         "Winner": "Player Strong", "Loser": "Player Weak", "WRank": 5, "LRank": 95}
        for date in pd.date_range("2023-12-01", periods=80)
    ])


def test_calibration_reserves_newest_season_and_serializes_exact_coefficients(tmp_path, monkeypatch):
    coefficients = np.array([3.123456789, 2.123456789, 1.123456789, 1.923456789])
    training_lengths = []
    def fit(features, labels):
        training_lengths.append(len(features))
        return coefficients
    monkeypatch.setattr("backtest.calibrate_weights._fit_logistic_weights", fit)
    path = tmp_path / "model.json"
    model = calibrate_from_dataframe(archive_rows(), str(path))
    clay = model["surfaces"]["clay"]
    assert clay["status"] == "validated"
    assert clay["trained_through"] == "2023-12-31"
    assert clay["validation_from"] == "2024-01-01"
    assert training_lengths == [28]
    assert clay["training_samples"] == 28
    assert clay["validation_samples"] == 49
    assert clay["weights"] == coefficients.tolist()
    assert load_model(path) == model == json.loads(path.read_text())
    assert get_weights("Clay", model, "2024-01-01") == BASELINE_WEIGHTS
    assert get_weights("Clay", model, clay["validated_through"]) == BASELINE_WEIGHTS
    assert get_weights("Clay", model, "2025-01-01") == coefficients.tolist()


def test_bad_holdout_keeps_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr("backtest.calibrate_weights._fit_logistic_weights", lambda *args: np.zeros(4))
    result = calibrate_from_dataframe(archive_rows(), str(tmp_path / "model.json"))
    entry = result["surfaces"]["clay"]
    assert entry["status"] == "baseline"
    assert entry["weights"] == list(BASELINE_WEIGHTS)
    assert entry["validation_metrics"]["candidate_brier"] > entry["validation_metrics"]["baseline_brier"]


@pytest.mark.parametrize("frame", [pd.DataFrame(), archive_rows().iloc[:10]])
def test_insufficient_history_is_explicit_baseline(tmp_path, frame):
    result = calibrate_from_dataframe(frame, str(tmp_path / "model.json"))
    assert all(entry["status"] == "baseline" for entry in result["surfaces"].values())


def test_actual_optimizer_reports_holdout_metrics(tmp_path):
    result = calibrate_from_dataframe(archive_rows(), str(tmp_path / "model.json"))
    entry = result["surfaces"]["clay"]
    assert entry["trained_through"] < entry["validation_from"]
    assert all(np.isfinite(value) for value in entry["validation_metrics"].values())
    if entry["status"] == "validated":
        assert entry["validation_metrics"]["candidate_brier"] < entry["validation_metrics"]["baseline_brier"]


def test_same_day_never_straddles_split(tmp_path):
    frame = pd.concat([archive_rows(), archive_rows().assign(Tournament="Other")], ignore_index=True)
    result = calibrate_from_dataframe(frame, str(tmp_path / "model.json"), validation_start="2024-01-10")
    entry = result["surfaces"]["clay"]
    assert entry["trained_through"] == "2024-01-09"
    assert entry["validation_from"] == "2024-01-10"
