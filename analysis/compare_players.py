"""Comparaison des attributs joueurs et calcul des cotes du modèle."""

from math import ceil, floor
from typing import Any, Tuple
from core.models import MatchAnalysisData


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        str_val = str(val).strip()
        return float(str_val) if str_val else default
    except (ValueError, TypeError):
        return default


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


def _compute_odds_pair(score_a: float, score_b: float) -> Tuple[float, float]:
    total = score_a + score_b
    trj = 0.9
    if score_a <= score_b:
        odds_a = round(trj * total / (score_a + 1e-3), 2)
        odds_b = round(1 / (1 / trj - 1 / odds_a), 2)
    else:
        odds_b = round(trj * total / (score_b + 1e-3), 2)
        odds_a = round(1 / (1 / trj - 1 / odds_b), 2)
    return odds_a, odds_b


def _compare_typed_match(match: MatchAnalysisData) -> MatchAnalysisData:
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
    pa.model_odds, pb.model_odds = _compute_odds_pair(score_a, score_b)
    return match


def _compare_legacy_array(data: Any) -> Any:
    """Compatibilité ascendante pour les anciens vecteurs match_vs (44 éléments)."""
    comparisons = [
        _score_diff(_safe_float(data[5]) - _safe_float(data[4]), step=5, use_floor=True),
        _score_diff(_safe_float(data[6]) - _safe_float(data[7]), step=1),
        _score_diff(_safe_float(data[8]) - _safe_float(data[9]), step=3),
        _score_diff(_safe_float(data[10]) - _safe_float(data[11]), step=5),
        _score_diff(_safe_float(data[12]) - _safe_float(data[13]), step=5),
        _score_binary(_safe_float(data[14]), _safe_float(data[25]), 10),
        _score_binary(_safe_float(data[15]), _safe_float(data[26]), 20),
        _score_binary(_safe_float(data[16]), _safe_float(data[27]), 20),
        _score_binary(_safe_float(data[17]), _safe_float(data[28]), 20),
        _score_binary(_safe_float(data[18]), _safe_float(data[29]), 20),
        _score_binary(_safe_float(data[19]), _safe_float(data[30]), 30),
        _score_binary(_safe_float(data[20]), _safe_float(data[31]), 10, invert=True),
        _score_binary(_safe_float(data[21]), _safe_float(data[32]), 10, invert=True),
        _score_binary(_safe_float(data[22]), _safe_float(data[33]), 20),
        _score_binary(_safe_float(data[23]), _safe_float(data[34]), 20),
        _score_binary(_safe_float(data[24]), _safe_float(data[35]), 20),
    ]
    score_a = sum(c[0] for c in comparisons) + _safe_float(data[42]) * 5
    score_b = sum(c[1] for c in comparisons) + _safe_float(data[43]) * 5
    data[36], data[37] = _compute_odds_pair(score_a, score_b)
    return data


def compare_players(match_data: Any) -> Any:
    """Calcule les cotes théoriques sur MatchAnalysisData ou un vecteur match_vs."""
    if isinstance(match_data, MatchAnalysisData):
        return _compare_typed_match(match_data)
    return _compare_legacy_array(match_data)