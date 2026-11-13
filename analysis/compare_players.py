"""Comparaison des attributs joueurs et calcul des cotes du modèle."""

from math import ceil, floor
from typing import Tuple
from core.models import MatchAnalysisData


def _score_diff(diff: float, step: int = 1, use_floor: bool = False) -> Tuple[int, int]:
    """Calcule le score comparatif (J1, J2) à partir d'un écart signé."""
    if diff == 0:
        return 0, 0
    fn = floor if use_floor else ceil
    if diff > 0:
        val = step * fn((diff - 1) / 10) if use_floor else step * fn(diff / 10)
        return val, 0
    val = step * fn((-diff - 1) / 10) if use_floor else step * fn(-diff / 10)
    return 0, val


def _score_binary(
    val_a: float, val_b: float, weight: int, invert: bool = False
) -> Tuple[int, int]:
    """Attribue le poids au joueur dominant (ou le moins fatigué si invert=True)."""
    if val_a == val_b:
        return weight // 2, weight // 2
    a_wins = (val_a < val_b) if invert else (val_a > val_b)
    return (weight, 0) if a_wins else (0, weight)


def compare_players(match: MatchAnalysisData) -> MatchAnalysisData:
    """Calcule les cotes théoriques (player_a.model_odds, player_b.model_odds)."""
    pa, pb = match.player_a, match.player_b
    h2h = match.h2h

    comparisons = [
        _score_diff(pb.ranking - pa.ranking, step=5, use_floor=True),
        _score_diff(h2h.all_time[0] - h2h.all_time[1], step=1),
        _score_diff(h2h.last_year[0] - h2h.last_year[1], step=3),
        _score_diff(h2h.surface[0] - h2h.surface[1], step=5),
        _score_diff(h2h.games[0] - h2h.games[1], step=5),
        _score_binary(pa.win_pct_last_10, pb.win_pct_last_10, 10),
        _score_binary(pa.win_pct_last_50, pb.win_pct_last_50, 20),
        _score_binary(pa.win_pct_1y, pb.win_pct_1y, 20),
        _score_binary(pa.win_pct_career, pb.win_pct_career, 20),
        _score_binary(pa.win_pct_1y_surface, pb.win_pct_1y_surface, 20),
        _score_binary(pa.win_pct_career_surface, pb.win_pct_career_surface, 30),
        _score_binary(pa.matches_last_month, pb.matches_last_month, 10, invert=True),
        _score_binary(pa.tournament_minutes, pb.tournament_minutes, 10, invert=True),
        _score_binary(pa.first_serve_pct, pb.first_serve_pct, 20),
        _score_binary(pa.first_serve_pts_won, pb.first_serve_pts_won, 20),
        _score_binary(pa.break_points_saved_pct, pb.break_points_saved_pct, 20),
    ]

    score_a = sum(c[0] for c in comparisons) + pa.odds_spread * 5
    score_b = sum(c[1] for c in comparisons) + pb.odds_spread * 5
    total = score_a + score_b

    trj = 0.9
    if score_a <= score_b:
        odds_a = round(trj * total / (score_a + 1e-3), 2)
        odds_b = round(1 / (1 / trj - 1 / odds_a), 2)
    else:
        odds_b = round(trj * total / (score_b + 1e-3), 2)
        odds_a = round(1 / (1 / trj - 1 / odds_b), 2)

    pa.model_odds, pb.model_odds = odds_a, odds_b
    return match