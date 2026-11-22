"""Tests de non-régression pour les correctifs Priorité 1."""

import importlib
import json
from bs4 import BeautifulSoup
import pandas as pd

from analysis.compare_players import _compute_odds_pair, _load_surface_weights, compare_players
from analysis.h2h_stats import H2HStats
from analysis.h2h_table import H2HDataProcessor
from analysis.indice_confiance import MotivationAnalyzer
from backtest.calibrate_weights import calibrate_from_dataframe
from core.analyze_match import _populate_elo_ratings
from core.database import TennisDatabase
from core.models import ConfidenceMetrics, MatchAnalysisData, PlayerStats
from data_providers.elo_matcher import EloMatcher
from strategy.alpha_strategy import evaluate_alpha_strategy
from strategy.result_settler import _is_match_live, _parse_match_outcome


def test_elo_matcher_extracts_grass_and_handles_missing_slot():
    """Vérifie que Grass extrait bien la 3e colonne et qu'un '-' ne décale pas les colonnes."""
    elo_sample = (
        "Carlos Alcaraz 2150.5 2100.2 2180.4\n"
        "Felix Auger-Aliassime 1900.0 - 1820.5\n"
    )
    assert EloMatcher.find_elo_ratings(
        elo_sample, "Carlos Alcaraz", "Felix Auger-Aliassime", "Grass"
    ) == ("2180.4", "1820.5")
    assert EloMatcher.find_elo_ratings(
        elo_sample, "Carlos Alcaraz", "Felix Auger-Aliassime", "Clay"
    ) == ("2100.2", "")


def test_elo_populated_before_compare_players_changes_odds():
    """Vérifie que le chargement ELO avant compare_players influe bien sur model_odds."""
    elo_sample = "Jannik Sinner 2200.0 2100.0 2050.0\nTaylor Fritz 1850.0 1750.0 1800.0\n"
    match_without_elo = MatchAnalysisData(
        match_url="https://tennisinsight.com/match/1/2026-atp/r16/sinner-vs-fritz",
        surface="Hard",
        player_a=PlayerStats(name="Jannik Sinner", ranking=5),
        player_b=PlayerStats(name="Taylor Fritz", ranking=5),
    )
    match_with_elo = MatchAnalysisData(
        match_url="https://tennisinsight.com/match/1/2026-atp/r16/sinner-vs-fritz",
        surface="Hard",
        player_a=PlayerStats(name="Jannik Sinner", ranking=5),
        player_b=PlayerStats(name="Taylor Fritz", ranking=5),
    )
    _populate_elo_ratings(elo_sample, match_with_elo)
    compare_players(match_without_elo)
    compare_players(match_with_elo)

    assert match_with_elo.player_a.elo == 2200.0
    assert match_with_elo.player_a.model_odds < match_without_elo.player_a.model_odds


def test_compute_odds_pair_handles_zero_and_negative_scores():
    """Vérifie l'absence de ZeroDivisionError et de cotes négatives."""
    assert _compute_odds_pair(0.0, 0.0, trj=0.90) == (1.8, 1.8)
    odds_a, odds_b = _compute_odds_pair(-50.0, 120.0, trj=0.90)
    assert odds_a > odds_b >= 0.90


def test_alpha_strategy_accepts_strong_favorite_model_odds_below_101():
    """Vérifie qu'une cote modèle à 0.95 (TRJ=0.90) n'est pas rejetée comme donnée incomplète."""
    res = evaluate_alpha_strategy(
        model_1=0.95,
        model_2=16.0,
        book_1=1.45,
        book_2=2.85,
        elo_1=2150.0,
        elo_2=1850.0,
        player_1="Jannik Sinner",
        player_2="Opponent",
    )
    assert res["bet_recommended"] is True
    assert res["selected_player"] == "Jannik Sinner"


def test_load_surface_weights_ignores_degraded_calibration(tmp_path, monkeypatch):
    """Vérifie le repli sur les poids par défaut si brier_after > brier_before."""
    bad_json = tmp_path / "calibrated_weights.json"
    bad_json.write_text(
        json.dumps({"hard": {"form": 1.0, "surface": 1.0, "brier_before": 0.22, "brier_after": 0.25}}),
        encoding="utf-8",
    )
    cp_mod = importlib.import_module("analysis.compare_players")
    monkeypatch.setattr(cp_mod, "CALIBRATED_WEIGHTS_PATH", str(bad_json))
    weights = _load_surface_weights("Hard")
    assert weights["form"] == 20.0
    assert weights["surface"] == 30.0


def test_result_settler_unicode_accents_void_and_live():
    """Vérifie le parsing Unicode, l'abandon 1er set vs 2e set et la détection live."""
    html_unicode = (
        '<div class="wrapper"><div class="match-preview-header">'
        "Roland Garros Final: Iga Świątek def. Karolina Muchova 6-2 6-4"
        "</div></div>"
    )
    winner, is_void = _parse_match_outcome(
        html_unicode, player_a="Iga Swiatek", player_b="Karolina Muchova"
    )
    assert winner == "Iga Swiatek"
    assert is_void is False

    html_ret_set1 = (
        '<div><div class="match-preview-header">'
        "Sebastián Báez def. Botic van de Zandschulp 3-2 ret."
        "</div></div>"
    )
    winner_r1, is_void_r1 = _parse_match_outcome(
        html_ret_set1, player_a="Sebastian Baez", player_b="Botic van de Zandschulp"
    )
    assert winner_r1 == "Sebastian Baez"
    assert is_void_r1 is True

    html_ret_set2 = (
        '<div><div class="match-preview-header">'
        "Sebastián Báez def. Botic van de Zandschulp 7-6(4) 2-1 ret."
        "</div></div>"
    )
    _, is_void_r2 = _parse_match_outcome(
        html_ret_set2, player_a="Sebastian Baez", player_b="Botic van de Zandschulp"
    )
    assert is_void_r2 is False
    assert _is_match_live("Match In Progress - Set 2") is True


def test_database_settle_bet_handles_accents_and_aliases(tmp_path):
    """Vérifie que settle_bet reconnaît les accents et alias (Cori/Coco Gauff)."""
    db = TennisDatabase(db_path=str(tmp_path / "test_unicode.db"))
    match = MatchAnalysisData(
        match_url="https://tennisinsight.com/match/777/2026-wta/qf/gauff-vs-swiatek",
        tournament="Madrid WTA 1000",
        surface="Clay",
        player_a=PlayerStats(name="Coco Gauff", model_odds=1.50, book_odds=1.80, elo=2050.0),
        player_b=PlayerStats(name="Iga Swiatek", model_odds=2.40, book_odds=2.05, elo=1880.0),
    )
    db.save_bet(
        match,
        {
            "bet_recommended": True,
            "selected_player": "Coco Gauff",
            "book_odds": 1.80,
            "model_odds": 1.50,
            "model_prob": 0.62,
            "ev_percent": 11.6,
            "elo_diff": 170.0,
            "kelly_stake_pct": 2.0,
        },
    )
    db.settle_bet(match.match_url, "Cori Gauff", is_void=False)
    roi = db.get_roi_summary()
    assert roi["won"] == 1
    assert roi["profit"] == 1.6


def test_h2h_ignores_empty_winner_and_matches_surface_for_tactics():
    """Vérifie qu'un vainqueur vide n'est plus crédité à J2 et que le H2H tactique filtre par surface."""
    stats = H2HStats("Carlos Alcaraz", "Jannik Sinner")
    stats.update_stats("", 0.0, "Hard", "6-4 6-4", "Hard")
    assert stats.p_a.wins_all == 0
    assert stats.p_b.wins_all == 0

    html = """
    <div class="h2h-matches">
      <table>
        <tr><th>Date</th><th>Tour</th><th>Surface</th><th>Winner</th><th>Score</th></tr>
        <tr><td>Jan 10 2026</td><td>AO</td><td>Hard</td><td>Jannik Sinner</td><td><a href="/match/111/">6-4 6-4</a></td></tr>
        <tr><td>May 20 2025</td><td>RG</td><td>Clay</td><td>Carlos Alcaraz</td><td><a href="/match/222/">6-3 6-2</a></td></tr>
      </table>
    </div>
    """
    match = MatchAnalysisData(
        match_url="https://tennisinsight.com/match/999/2026-rg/f/alcaraz-vs-sinner",
        surface="Clay",
        player_a=PlayerStats(name="Carlos Alcaraz"),
        player_b=PlayerStats(name="Jannik Sinner"),
    )
    proc = H2HDataProcessor(BeautifulSoup(html, "lxml"), match)
    proc.process()
    assert proc.go_url == "/match/222/"
    assert proc.flag == 0


def test_motivation_masters_and_slam_is_100():
    """Vérifie que les tournois 1000 et Grand Chelem attribuent 100.0 de motivation."""
    conf = ConfidenceMetrics()
    analyzer = MotivationAnalyzer(data_fetcher=None, admin_url="", confidence=conf)
    analyzer.calculate_motivation_index("ATP Masters 1000", nb_matchs=1, flag=0)
    analyzer.calculate_motivation_index("Grand Slam", nb_matchs=0, flag=1)
    assert conf.motivation_a == 100.0
    assert conf.motivation_b == 100.0


def test_calibration_handles_nan_ranks_and_preserves_scale(tmp_path):
    """Vérifie la gestion des rangs NaN et l'équilibre form + surface = 50."""
    rows = []
    for idx in range(50):
        rows.append({
            "Date": f"2024-{(idx // 25) + 1:02d}-{(idx % 25) + 1:02d}",
            "Surface": "Hard",
            "Comment": "Completed",
            "Winner": "Player Strong" if idx % 4 != 0 else "Player Weak",
            "Loser": "Player Weak" if idx % 4 != 0 else "Player Strong",
            "WRank": None if idx == 10 else 10,
            "LRank": 120,
        })
    out = str(tmp_path / "weights.json")
    res = calibrate_from_dataframe(pd.DataFrame(rows), output_path=out)
    assert res["hard"]["form"] + res["hard"]["surface"] == 50.0
    assert res["hard"]["brier_after"] <= res["hard"]["brier_before"]

def test_h2h_parses_real_tennisinsight_six_column_layout():
    """Vérifie le parsing du format réel TennisInsight (Date, Tournament+Surface, Players, Result, Odds)."""
    html = """
    <div class="h2h-matches">
      <table>
        <tr><th>Date</th><th>Tournament</th><th>Players</th><th>Result</th><th>Odds</th><th></th></tr>
        <tr>
          <td>Jan 19 2026</td>
          <td>Australian Open Slam (AUS) Hard Court, SF</td>
          <td>(1) Alcaraz (1, 3.24) d (3) Zverev (3, 2.03)</td>
          <td><a href="/match/1001/">6-4 7-6(5) 6-7(3) 6-7(4) 7-5</a></td>
          <td>$1.193 $5.596</td>
          <td></td>
        </tr>
        <tr>
          <td>Aug 7 2025</td>
          <td>Cincinnati TMS (USA) Hard Court, SF</td>
          <td>(2) Alcaraz (2, 2.87) d (3) Zverev (3, 2.33)</td>
          <td><a href="/match/1002/">6-4 6-3</a></td>
          <td>$1.538 $2.727</td>
          <td></td>
        </tr>
        <tr>
          <td>Nov 11 2024</td>
          <td>Tennis Masters Cup (ITA) Indoor Hard, RR</td>
          <td>(2) Zverev (6, 1.90) d (3) Alcaraz (2, 2.12)</td>
          <td><a href="/match/1003/">7-6(5) 6-4</a></td>
          <td>$2.004 $1.931</td>
          <td></td>
        </tr>
      </table>
    </div>
    """
    match = MatchAnalysisData(
        match_url="https://tennisinsight.com/match/260684301/2026-turin-atp-wtf/f/alexander-zverev-vs-carlos-alcaraz/",
        surface="Indoor Hard",
        player_a=PlayerStats(name="Alexander Zverev"),
        player_b=PlayerStats(name="Carlos Alcaraz"),
    )
    proc = H2HDataProcessor(BeautifulSoup(html, "lxml"), match)
    proc.process()

    assert match.h2h.all_time == (33.33, 66.67)
    assert match.h2h.surface == (100.0, 0.0)
    assert match.h2h.games == (47.57, 52.43)
    assert proc.go_url == "/match/1003/"
    assert proc.flag == 0
