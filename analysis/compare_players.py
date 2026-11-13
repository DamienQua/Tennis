"""Comparaison des attributs joueurs et calcul des cotes du modèle (calibrable par surface)."""

import json
from math import ceil, floor
import os
from typing import Any, Dict, Tuple
from core.models import MatchAnalysisData

CALIBRATED_WEIGHTS_PATH = "config/calibrated_weights.json"

_DEFAULT_WEIGHTS: Dict[str, Dict[str, float]] = {
    "hard": {"rank": 5.0, "form": 20.0, "surface": 30.0, "elo": 0.0, "trj": 0.90},
    "clay": {"rank": 5.0, "form": 20.0, "surface": 30.0, "elo": 0.0, "trj": 0.90},
    "grass": {"rank": 5.0, "form": 20.0, "surface": 30.0, "elo": 0.0, "trj": 0.90},
}


def _load_surface_weights(surface: str) -> Dict[str, float]:
    s_low = surface.strip().lower()
    bucket = "clay" if "clay" in s_low else ("grass" if "grass" in s_low else "hard")
    if os.path.exists(CALIBRATED_WEIGHTS_PATH):
        try:
            with open(CALIBRATED_WEIGHTS_PATH, "r", encoding="utf-8") as f_in:
                data = json.load(f_in)
            if bucket in data:
                return {**_DEFAULT_WEIGHTS[bucket], **data[bucket]}
        except (OSError, ValueError, TypeError):
            pass
    return _DEFAULT_WEIGHTS[bucket]


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        str_val = str(val).strip()
        return float(str_val) if str_val else default
    except (ValueError, TypeError):
        return default


def _score_diff(diff: float, step: float = 1.0, use_floor: bool = False) -> Tuple[float, float]:
    """Calcule le score comparatif (J1, J2) à partir d'un écart signé."""
    if diff == 0:
        return 0.0, 0.0
    fn = floor if use_floor else ceil
    if diff > 0:
        val = step * fn((diff - 1) / 10) if use_floor else step * fn(diff / 10)
        return float(val), 0.0
    val = step * fn((-diff - 1) / 10) if use_floor else step * fn(-diff / 10)
    return 0.0, float(val)


def _score_binary(
    val_a: float, val_b: float, weight: float, invert: bool = False
) -> Tuple[float, float]:
    """Attribue le poids au joueur dominant (ou le moins fatigué si invert=True)."""
    if val_a == val_b:
        return weight / 2.0, weight / 2.0
    a_wins = (val_a < val_b) if invert else (val_a > val_b)
    return (weight, 0.0) if a_wins else (0.0, weight)


def _compute_odds_pair(
    score_a: float, score_b: float, trj: float = 0.90
) -> Tuple[float, float]:
    total = score_a + score_b
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
    weights = _load_surface_weights(match.surface)
    w_form = weights["form"]
    w_surf = weights["surface"]

    comparisons = [
        _score_diff(pb.ranking - pa.ranking, step=weights["rank"], use_floor=True),
        _score_diff(h2h.all_time[0] - h2h.all_time[1], step=1.0),
        _score_diff(h2h.last_year[0] - h2h.last_year[1], step=3.0),
        _score_diff(h2h.surface[0] - h2h.surface[1], step=5.0),
        _score_diff(h2h.games[0] - h2h.games[1], step=5.0),
        _score_binary(pa.win_pct_last_10, pb.win_pct_last_10, w_form * 0.5),
        _score_binary(pa.win_pct_last_50, pb.win_pct_last_50, w_form),
        _score_binary(pa.win_pct_1y, pb.win_pct_1y, w_form),
        _score_binary(pa.win_pct_career, pb.win_pct_career, w_form),
        _score_binary(pa.win_pct_1y_surface, pb.win_pct_1y_surface, w_surf * (2.0 / 3.0)),
        _score_binary(pa.win_pct_career_surface, pb.win_pct_career_surface, w_surf),
        _score_binary(pa.matches_last_month, pb.matches_last_month, 10.0, invert=True),
        _score_binary(pa.tournament_minutes, pb.tournament_minutes, 10.0, invert=True),
        _score_binary(pa.first_serve_pct, pb.first_serve_pct, 20.0),
        _score_binary(pa.first_serve_pts_won, pb.first_serve_pts_won, 20.0),
        _score_binary(pa.break_points_saved_pct, pb.break_points_saved_pct, 20.0),
    ]

    elo_bonus_a = max(0.0, (pa.elo - pb.elo) * weights["elo"]) if (pa.elo > 0 and pb.elo > 0) else 0.0
    elo_bonus_b = max(0.0, (pb.elo - pa.elo) * weights["elo"]) if (pa.elo > 0 and pb.elo > 0) else 0.0

    score_a = sum(c[0] for c in comparisons) + pa.odds_spread * 5.0 + elo_bonus_a
    score_b = sum(c[1] for c in comparisons) + pb.odds_spread * 5.0 + elo_bonus_b
    pa.model_odds, pb.model_odds = _compute_odds_pair(score_a, score_b, trj=weights["trj"])
    return match


def _compare_legacy_array(data: Any) -> Any:
    """Compatibilité ascendante pour les anciens vecteurs match_vs (44 éléments)."""
    comparisons = [
        _score_diff(_safe_float(data[5]) - _safe_float(data[4]), step=5.0, use_floor=True),
        _score_diff(_safe_float(data[6]) - _safe_float(data[7]), step=1.0),
        _score_diff(_safe_float(data[8]) - _safe_float(data[9]), step=3.0),
        _score_diff(_safe_float(data[10]) - _safe_float(data[11]), step=5.0),
        _score_diff(_safe_float(data[12]) - _safe_float(data[13]), step=5.0),
        _score_binary(_safe_float(data[14]), _safe_float(data[25]), 10.0),
        _score_binary(_safe_float(data[15]), _safe_float(data[26]), 20.0),
        _score_binary(_safe_float(data[16]), _safe_float(data[27]), 20.0),
        _score_binary(_safe_float(data[17]), _safe_float(data[28]), 20.0),
        _score_binary(_safe_float(data[18]), _safe_float(data[29]), 20.0),
        _score_binary(_safe_float(data[19]), _safe_float(data[30]), 30.0),
        _score_binary(_safe_float(data[20]), _safe_float(data[31]), 10.0, invert=True),
        _score_binary(_safe_float(data[21]), _safe_float(data[32]), 10.0, invert=True),
        _score_binary(_safe_float(data[22]), _safe_float(data[33]), 20.0),
        _score_binary(_safe_float(data[23]), _safe_float(data[34]), 20.0),
        _score_binary(_safe_float(data[24]), _safe_float(data[35]), 20.0),
    ]
    score_a = sum(c[0] for c in comparisons) + _safe_float(data[42]) * 5.0
    score_b = sum(c[1] for c in comparisons) + _safe_float(data[43]) * 5.0
    data[36], data[37] = _compute_odds_pair(score_a, score_b)
    return data


def compare_players(match_data: Any) -> Any:
    """Calcule les cotes théoriques sur MatchAnalysisData ou un vecteur match_vs."""
    if isinstance(match_data, MatchAnalysisData):
        return _compare_typed_match(match_data)
    return _compare_legacy_array(match_data)