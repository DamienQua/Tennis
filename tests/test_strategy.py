"""Tests unitaires pour la stratégie Alpha 5+, Kelly et le modèle de cotes."""

from analysis.compare_indice import compare_indice
from analysis.compare_players import compare_players
from core.models import ConfidenceMetrics, H2HMetrics, MatchAnalysisData, PlayerStats
from strategy.alpha_strategy import calculate_kelly_stake, evaluate_alpha_strategy


def _build_sample_match(
    model_a: float = 1.45,
    model_b: float = 2.60,
    book_a: float = 1.75,
    book_b: float = 2.15,
    elo_a: float = 2050.0,
    elo_b: float = 1850.0,
) -> MatchAnalysisData:
    return MatchAnalysisData(
        match_url="https://tennisinsight.com/match/999/2026-paris-masters/qf/a-vs-b",
        tournament="Paris Masters",
        surface="Indoor Hard",
        player_a=PlayerStats(
            name="Jannik Sinner",
            ranking=1,
            elo=elo_a,
            model_odds=model_a,
            book_odds=book_a,
            win_pct_last_10=90.0,
            win_pct_last_50=88.0,
            win_pct_1y=89.0,
            win_pct_career=82.0,
            win_pct_1y_surface=91.0,
            win_pct_career_surface=85.0,
            first_serve_pct=65.0,
            first_serve_pts_won=79.0,
            break_points_saved_pct=70.0,
        ),
        player_b=PlayerStats(
            name="Taylor Fritz",
            ranking=6,
            elo=elo_b,
            model_odds=model_b,
            book_odds=book_b,
            win_pct_last_10=70.0,
            win_pct_last_50=72.0,
            win_pct_1y=71.0,
            win_pct_career=68.0,
            win_pct_1y_surface=74.0,
            win_pct_career_surface=70.0,
            first_serve_pct=62.0,
            first_serve_pts_won=75.0,
            break_points_saved_pct=64.0,
        ),
        h2h=H2HMetrics(
            all_time=(75.0, 25.0),
            last_year=(100.0, 0.0),
            surface=(75.0, 25.0),
            games=(58.0, 42.0),
        ),
    )


def test_alpha_strategy_triggers_valid_signal():
    """Vérifie qu'un pari est conseillé quand EV > 3%, ΔELO >= 150 et cote in [1.40, 2.50]."""
    match = _build_sample_match()
    res = evaluate_alpha_strategy(match)

    assert res["bet_recommended"] is True
    assert res["selected_player"] == "Jannik Sinner"
    assert res["player_index"] == 1
    assert res["ev_percent"] > 3.0
    assert res["elo_diff"] == 200.0
    assert 0.0 < res["kelly_stake_pct"] <= 3.0


def test_alpha_strategy_rejects_insufficient_elo_gap():
    """Vérifie le rejet si l'écart ELO est inférieur à 150 points."""
    match = _build_sample_match(elo_a=1950.0, elo_b=1850.0)
    res = evaluate_alpha_strategy(match)

    assert res["bet_recommended"] is False
    assert res["selected_player"] == ""


def test_alpha_strategy_rejects_out_of_bounds_odds():
    """Vérifie le rejet si la cote bookmaker est hors de [1.40, 2.50]."""
    match_low = _build_sample_match(book_a=1.35)
    match_high = _build_sample_match(book_a=2.55)

    assert evaluate_alpha_strategy(match_low)["bet_recommended"] is False
    assert evaluate_alpha_strategy(match_high)["bet_recommended"] is False


def test_kelly_stake_calculation_and_cap():
    """Vérifie le calcul du quart de Kelly et le plafonnement à 3%."""
    stake_zero = calculate_kelly_stake(prob=0.40, book_odds=2.00)
    stake_capped = calculate_kelly_stake(prob=0.90, book_odds=2.40)

    assert stake_zero == 0.0
    assert stake_capped == 3.0


def test_compare_players_and_indice():
    """Vérifie le calcul des cotes modèle et de l'indice de confiance."""
    match = _build_sample_match(model_a=0.0, model_b=0.0)
    match.confidence = ConfidenceMetrics(
        motivation_a=100.0,
        surface_rank_a=50.0,
        motivation_b=50.0,
        surface_rank_b=20.0,
        book_fav_bonus=(20.0, 0.0),
        model_fav_bonus=(40.0, 0.0),
    )

    compare_players(match)
    assert 0.90 <= match.player_a.model_odds < match.player_b.model_odds

    final_idx = compare_indice(match)
    assert final_idx == 3.0
    assert match.confidence.final_index == 3.0