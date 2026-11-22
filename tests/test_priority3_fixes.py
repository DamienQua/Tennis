"""Tests de non-régression pour les correctifs Priorité 3."""

import pandas as pd
from analysis.compare_players import compare_players
from backtest.point_in_time_backtest import PointInTimeBacktester
from backtest.point_in_time_stats import INITIAL_ELO, PointInTimeStats
from core.models import MatchAnalysisData, PlayerStats
from utils.helpers import normalize_surface, normalize_text, safe_float, safe_int


def test_factorized_utils_helpers():
    """Vérifie safe_float, safe_int, normalize_surface et normalize_text."""
    assert safe_float("1,75") == 1.75
    assert safe_float("bad", default=-1.0) == -1.0
    assert safe_int("42.0") == 42
    assert safe_int(None, default=1000) == 1000
    assert normalize_surface("Indoor Hard") == "hard"
    assert normalize_surface("Red Clay") == "clay"
    assert normalize_surface("Grass Court") == "grass"
    assert normalize_text("Iga Świątek — Łukasz") == "iga swiatek — lukasz"


def test_point_in_time_elo_updates_after_previous_match():
    """Vérifie que get_player_elo_before renvoie bien l'ELO APRÈS le match précédent."""
    matches = pd.DataFrame([
        {"Date": "2024-01-10", "Winner": "Player A", "Loser": "Player B", "Surface": "Hard"},
    ])
    stats = PointInTimeStats(matches)

    # Avant ou le jour même du 1er match : 1500.0
    assert stats.get_player_elo_before("Player A", pd.Timestamp("2024-01-10"), "Hard") == INITIAL_ELO
    # Après le 1er match : ELO mis à jour (+16 pour A, -16 pour B)
    assert stats.get_player_elo_before("Player A", pd.Timestamp("2024-01-20"), "Hard") > INITIAL_ELO
    assert stats.get_player_elo_before("Player B", pd.Timestamp("2024-01-20"), "Hard") < INITIAL_ELO


def test_point_in_time_backtester_uses_production_compare_players(tmp_path):
    """Vérifie que PointInTimeBacktester produit exactement les mêmes cotes que compare_players."""
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "results"
    data_dir.mkdir()

    df = pd.DataFrame([
        {
            "Date": "2024-01-05",
            "Tournament": "Brisbane",
            "Surface": "Hard",
            "Comment": "Completed",
            "Winner": "Sinner J.",
            "Loser": "Fritz T.",
            "WRank": 2,
            "LRank": 12,
            "PSW": 1.35,
            "PSL": 3.40,
        },
        {
            "Date": "2024-01-20",
            "Tournament": "Australian Open",
            "Surface": "Hard",
            "Comment": "Completed",
            "Winner": "Sinner J.",
            "Loser": "Fritz T.",
            "WRank": 2,
            "LRank": 12,
            "PSW": 1.45,
            "PSL": 2.95,
        },
    ])
    df.to_excel(data_dir / "atp_2024.xlsx", index=False)

    backtester = PointInTimeBacktester(
        data_dir=str(data_dir), output_dir=str(out_dir), strategy_mode="alpha_5_plus"
    )
    summary = backtester.run_backtest_for_year(
        year=2024, gender="atp", elo_data="Jannik Sinner 2400.0 2400.0 2400.0\n"
    )
    assert "total_bets" in summary
    assert len(backtester.records) == 2

    # Vérifie l'absence de look-ahead bias (match 1 doit partir à ELO=1500 malgré elo_data=2400)
    assert backtester.records[0]["elo_w"] == INITIAL_ELO
    # Vérifie que le match 2 reflète bien la victoire du match 1
    assert backtester.records[1]["elo_w"] > INITIAL_ELO

    # Vérifie que les cotes du match 2 coïncident exactement avec compare_players()
    stats = PointInTimeStats(df)
    m2_date = pd.Timestamp("2024-01-20")
    ref = MatchAnalysisData(
        match_url="",
        surface="Hard",
        player_a=PlayerStats(
            name="Sinner J.",
            ranking=2,
            elo=stats.get_player_elo_before("Sinner J.", m2_date, "Hard"),
            win_pct_last_10=100.0,
            win_pct_last_50=100.0,
            win_pct_1y=100.0,
            win_pct_career=100.0,
            win_pct_1y_surface=100.0,
            win_pct_career_surface=100.0,
            matches_last_month=1,
        ),
        player_b=PlayerStats(
            name="Fritz T.",
            ranking=12,
            elo=stats.get_player_elo_before("Fritz T.", m2_date, "Hard"),
            win_pct_last_10=0.0,
            win_pct_last_50=0.0,
            win_pct_1y=0.0,
            win_pct_career=0.0,
            win_pct_1y_surface=0.0,
            win_pct_career_surface=0.0,
            matches_last_month=1,
        ),
        h2h=stats.get_h2h_before("Sinner J.", "Fritz T.", m2_date, "Hard"),
    )
    compare_players(ref)
    assert backtester.records[1]["model_w"] == ref.player_a.model_odds
    assert backtester.records[1]["model_l"] == ref.player_b.model_odds
