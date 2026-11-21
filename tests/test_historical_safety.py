"""Synthetic archive fixtures cover rematches, ambiguity and temporal leakage."""

import asyncio
import math
from pathlib import Path
import subprocess
import sys
import pandas as pd
import pytest

from backtest.historical_odds import HistoricalOddsProvider
from backtest.point_in_time_backtest import PointInTimeBacktester
from backtest.point_in_time_stats import PointInTimeStats
from backtest.run_backtest import run_tournament_backtest
from backtest.consolidate_january import consolidate_january


def archive(tmp_path, rows):
    pd.DataFrame(rows).to_excel(tmp_path / "atp_2023.xlsx", index=False)
    return HistoricalOddsProvider(str(tmp_path))


def historical_row(date="2023-01-07", tournament="Adelaide", **kwargs):
    return dict(Date=date, Tournament=tournament, Winner="Djokovic N.", Loser="Medvedev D.",
                Comment="Completed", B365W=1.60, B365L=2.30, **kwargs)


def test_rematch_lookup_requires_exact_date_and_tournament(tmp_path):
    first = historical_row()
    second = historical_row("2023-03-03", "Dubai")
    second.update(Winner="Medvedev D.", Loser="Djokovic N.", B365W=2.5, B365L=1.5)
    provider = archive(tmp_path, [first, second])
    args = ("Novak Djokovic", "Daniil Medvedev", 2023)
    assert provider.get_match_odds(*args) is None
    assert provider.get_match_odds(*args, match_date="2023-03-03", tournament="Adelaide") is None
    result = provider.get_match_odds(*args, match_date="2023-03-03", tournament="Dubai")
    assert result["winner"] == "Daniil Medvedev"
    assert result["odds_a"]["b365"] == 1.5


def test_ambiguous_archive_rows_are_rejected(tmp_path):
    provider = archive(tmp_path, [historical_row(), historical_row()])
    assert provider.get_match_odds("Novak Djokovic", "Daniil Medvedev", 2023,
                                   match_date="2023-01-07", tournament="Adelaide") is None


def test_names_require_forenames_and_initials():
    match = HistoricalOddsProvider._name_matches
    assert match("Novak Djokovic", "Djokovic N.")
    assert match("Juan Manuel Cerundolo", "Cerundolo J.M.")
    assert not match("Francisco Cerundolo", "Cerundolo J.M.")
    assert not match("Djokovic", "Djokovic N.")
    assert not match("Novak Djokovic", "Djokovic D.")
    assert match("Botic van de Zandschulp", "Van De Zandschulp B.")


def test_noncompleted_results_and_nonfinite_odds_are_ignored(tmp_path):
    row = historical_row()
    row["Comment"] = "Retired"
    provider = archive(tmp_path, [row])
    assert provider.get_match_odds("Novak Djokovic", "Daniil Medvedev", 2023,
                                   match_date="2023-01-07", tournament="Adelaide") is None
    for missing in (float("nan"), float("inf"), None, ""):
        assert provider._extract_market_odds(pd.Series({"PSW": missing, "PSL": 2.2}), "PS") == (0, 0)


def test_elo_excludes_entire_current_day_and_includes_last_completed_day():
    frame = pd.DataFrame([
        {"Date": "2023-01-01", "Winner": "A", "Loser": "B", "Surface": "Hard"},
        {"Date": "2023-01-01", "Winner": "A", "Loser": "C", "Surface": "Hard"},
        {"Date": "2023-01-03", "Winner": "B", "Loser": "A", "Surface": "Hard"},
    ])
    stats = PointInTimeStats(frame)
    assert stats.get_player_elo_before("A", pd.Timestamp("2023-01-01 23:59"), "Hard") == 1500
    assert stats.get_player_elo_before("A", pd.Timestamp("2023-01-02"), "Hard") == 1532
    assert stats.get_player_elo_before("A", pd.Timestamp("2023-01-03"), "Hard") == 1532
    latest = stats.get_player_elo_before("A", pd.Timestamp("2023-01-04"), "Hard")
    assert latest < 1532
    assert latest == stats.get_player_elo_before("A", pd.Timestamp("2025-01-01"), "Hard")
    reversed_stats = PointInTimeStats(frame.iloc[::-1])
    assert latest == reversed_stats.get_player_elo_before("A", pd.Timestamp("2023-01-04"), "Hard")


def test_no_history_means_no_prediction_and_no_external_elo_fallback(tmp_path):
    frame = pd.DataFrame([dict(historical_row(), Surface="Hard", WRank=1, LRank=5)])
    frame.to_excel(tmp_path / "atp_2023.xlsx", index=False)
    stats = PointInTimeStats(frame)
    assert math.isnan(stats.get_player_stats_before("Djokovic N.", pd.Timestamp("2023-01-07"), "Hard")[0])
    runner = PointInTimeBacktester(data_dir=str(tmp_path), output_dir=str(tmp_path))
    with pytest.raises(ValueError, match="undated external ELO"):
        runner.run_backtest_for_year(2023, "atp", "Djokovic 2200 2200 2200")
    result = runner.run_backtest_for_year(2023, "atp")
    assert result["total_bets"] == 0
    assert result["skipped_missing_features"] == 1
    assert runner.records[0]["model_w"] == 0


def test_legacy_runner_uses_only_local_archives(tmp_path, monkeypatch):
    import socket
    def disallow_network(*args, **kwargs):
        raise AssertionError("Backtests must not access the network")
    monkeypatch.setattr(socket, "create_connection", disallow_network)
    archive(tmp_path, [dict(historical_row(), Surface="Hard", WRank=1, LRank=5)])
    result = asyncio.run(run_tournament_backtest("unused", "Adelaide", data_dir=str(tmp_path), output_dir=str(tmp_path)))
    assert result["total_matches"] == 1
    assert result["total_bets"] == 0


def test_january_consolidation_recomputes_from_archives_without_network(tmp_path, monkeypatch):
    import socket

    def disallow_network(*args, **kwargs):
        raise AssertionError("Consolidation must not fetch current ELO or statistics")

    monkeypatch.setattr(socket, "create_connection", disallow_network)
    frame = pd.DataFrame([dict(historical_row(), Surface="Hard", WRank=1, LRank=5)])
    for circuit in ("atp", "wta"):
        frame.to_excel(tmp_path / f"{circuit}_2023.xlsx", index=False)
    result = asyncio.run(consolidate_january(data_dir=str(tmp_path), output_dir=str(tmp_path)))
    assert result["total_matches"] == 2
    assert result["total_bets"] == 0
    assert "archive_errors" not in result
    assert (tmp_path / "january_2023_consolidated_backtest.xlsx").exists()


def test_future_matches_cannot_change_past_features():
    past = pd.DataFrame([
        {"Date": day, "Winner": "Player A", "Loser": "Player B", "Surface": "Hard"}
        for day in pd.date_range("2023-01-01", periods=5)
    ])
    future = pd.DataFrame([
        {"Date": day, "Winner": "Player B", "Loser": "Player A", "Surface": "Hard"}
        for day in pd.date_range("2023-02-01", periods=20)
    ])
    before = PointInTimeStats(past)
    after = PointInTimeStats(pd.concat([past, future], ignore_index=True))
    for player in ("Player A", "Player B"):
        assert before.get_player_stats_before(player, pd.Timestamp("2023-01-05"), "Hard") == after.get_player_stats_before(player, pd.Timestamp("2023-01-05"), "Hard")
        assert before.get_player_elo_before(player, pd.Timestamp("2023-01-05"), "Hard") == after.get_player_elo_before(player, pd.Timestamp("2023-01-05"), "Hard")


@pytest.mark.parametrize("script", ["run_backtest.py", "consolidate_january.py"])
def test_historical_script_help_works_outside_repository(script, tmp_path):
    target = Path(__file__).resolve().parents[1] / "backtest" / script
    result = subprocess.run([sys.executable, str(target), "--help"], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "--data-dir" in result.stdout
