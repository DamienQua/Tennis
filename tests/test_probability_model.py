"""Shared feature calculation and prediction must agree in every entry point."""

import importlib
import json
import numpy as np
import pandas as pd
import pytest

from analysis.compare_players import compare_players
from analysis.probability_model import BASELINE_WEIGHTS, baseline_model, build_features, get_weights, load_model, model_odds, predict_probabilities
from backtest.calibrate_weights import _extract_surface_samples
from backtest.point_in_time_backtest import PointInTimeBacktester
from backtest.point_in_time_stats import PointInTimeStats
from core.models import MatchAnalysisData, PlayerStats
from strategy.alpha_strategy import calculate_kelly_stake, evaluate_alpha_strategy
from strategy.generate_match_xlsx import _calculate_win_percentage


def test_live_legacy_backtest_and_training_prediction_parity(monkeypatch, tmp_path):
    frame = pd.DataFrame([
        {"Date": day, "Winner": "Player A", "Loser": "Player B", "Surface": "Hard",
         "WRank": 10, "LRank": 25, "Tournament": "Test"}
        for day in pd.date_range("2023-01-01", periods=5)
    ])
    stats = PointInTimeStats(frame)
    runner = PointInTimeBacktester(output_dir=str(tmp_path))
    row = frame.iloc[-1]
    extracted = runner._extract_row_features(row, stats)
    features = build_features(10, 25, extracted["form_w"], extracted["form_l"],
                              extracted["surf_w"], extracted["surf_l"], extracted["elo_w"], extracted["elo_l"])
    expected = model_odds(features, "Hard", baseline_model())
    monkeypatch.setattr(importlib.import_module("analysis.compare_players"), "load_model", baseline_model)
    match = MatchAnalysisData("test", player_a=PlayerStats(
        name="Player A", ranking=10, elo=extracted["elo_w"],
        win_pct_1y=extracted["form_w"], win_pct_career_surface=extracted["surf_w"]),
        player_b=PlayerStats(name="Player B", ranking=25, elo=extracted["elo_l"],
                            win_pct_1y=extracted["form_l"], win_pct_career_surface=extracted["surf_l"]))
    compare_players(match)
    assert (match.player_a.model_odds, match.player_b.model_odds) == expected
    legacy = [0.0] * 44
    legacy[1] = "Hard"
    for index, value in zip((4, 5, 16, 27, 19, 30, 40, 41),
                           (10, 25, extracted["form_w"], extracted["form_l"], extracted["surf_w"],
                            extracted["surf_l"], extracted["elo_w"], extracted["elo_l"])):
        legacy[index] = value
    compare_players(legacy)
    assert tuple(legacy[36:38]) == expected
    runner._process_single_row(row, stats)
    assert (runner.records[-1]["model_w"], runner.records[-1]["model_l"]) == expected
    sample = _extract_surface_samples(frame, stats).iloc[-1]
    assert sample["features"] == list(features)
    assert predict_probabilities(sample["features"]) == 1.0 / expected[0]
    assert 1.0 / expected[0] + 1.0 / expected[1] == pytest.approx(1)
    assert _calculate_win_percentage(expected[0]) == round(100.0 / expected[0], 2)


@pytest.mark.parametrize("index", range(8))
@pytest.mark.parametrize("invalid", [None, float("nan"), float("inf"), float("-inf")])
def test_features_reject_missing_or_nonfinite_inputs(index, invalid):
    values = [10, 20, 80, 60, 70, 50, 1800, 1600]
    values[index] = invalid
    with pytest.raises((ValueError, TypeError)):
        build_features(*values)


@pytest.mark.parametrize("field", ["ranking", "elo", "win_pct_1y", "win_pct_career_surface"])
def test_live_missing_feature_disables_prediction(field):
    player = PlayerStats(ranking=5, elo=1800, win_pct_1y=70, win_pct_career_surface=60)
    setattr(player, field, float("nan"))
    match = MatchAnalysisData("test", player_a=player,
                              player_b=PlayerStats(ranking=20, elo=1600, win_pct_1y=50, win_pct_career_surface=50))
    compare_players(match)
    assert match.player_a.model_odds == match.player_b.model_odds == 0


@pytest.mark.parametrize("index", range(6))
@pytest.mark.parametrize("invalid", [None, 0, float("nan"), float("inf"), float("-inf")])
def test_alpha_invalid_input_never_recommends(index, invalid):
    values = [1.25, 4.5, 1.5, 2.8, 2100, 0]
    values[5] = 1900
    values[index] = invalid
    result = evaluate_alpha_strategy(*values)
    assert not result["bet_recommended"]
    assert result["kelly_stake_pct"] == 0


def test_model_loader_rejects_old_format_and_unvalidated_coefficients(tmp_path):
    path = tmp_path / "model.json"
    path.write_text(json.dumps({"hard": {"rank": 5, "form": 20}}))
    assert load_model(path) == baseline_model()
    bad = baseline_model()
    bad["surfaces"]["hard"]["weights"] = [1, 2, 3, 4]
    path.write_text(json.dumps(bad))
    assert load_model(path) == baseline_model()
    bad["surfaces"]["hard"].update(status="validated", trained_through="2024-01-01",
                                   validation_from="2023-12-01", validated_through="2024-12-31")
    path.write_text(json.dumps(bad))
    assert load_model(path) == baseline_model()


def test_kelly_rejects_nonfinite_values():
    assert calculate_kelly_stake(float("nan"), 1.8) == 0
    assert calculate_kelly_stake(0.8, float("inf")) == 0


def validated_model():
    model = baseline_model()
    model["surfaces"]["hard"].update(
        status="validated", weights=[1.0, 1.0, 1.0, 1.0],
        trained_through="2023-12-31", validation_from="2024-01-01",
        validated_through="2024-12-31", training_samples=100, validation_samples=30,
        validation_metrics={"baseline_brier": 0.25, "candidate_brier": 0.20,
                            "baseline_log_loss": 0.70, "candidate_log_loss": 0.60},
    )
    return model


@pytest.mark.parametrize("field", ["training_samples", "validation_samples"])
@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), True, "100", 0, 100.5])
def test_model_loader_rejects_invalid_validation_counts(tmp_path, field, invalid):
    model = validated_model()
    model["surfaces"]["hard"][field] = invalid
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model))
    assert load_model(path) == baseline_model()


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -1])
def test_model_loader_rejects_invalid_weights(tmp_path, invalid):
    model = validated_model()
    model["surfaces"]["hard"]["weights"][0] = invalid
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model))
    assert load_model(path) == baseline_model()


@pytest.mark.parametrize("as_of", ["NaT", "", "not-a-date", float("nan")])
def test_unknown_prediction_date_cannot_use_validated_model(as_of):
    assert get_weights("Hard", validated_model(), as_of) == BASELINE_WEIGHTS


def test_future_validation_cannot_be_used_by_live_model():
    model = validated_model()
    model["surfaces"]["hard"]["validated_through"] = "9999-12-31"
    assert get_weights("Hard", model) == BASELINE_WEIGHTS
