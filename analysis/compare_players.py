"""Comparaison des attributs joueurs et calcul des cotes du modèle (calibrable par surface)."""

import json
import logging
from math import ceil, floor
import os
from typing import Any, Dict, Optional, Tuple
from core.models import MatchAnalysisData
from utils.helpers import normalize_surface

logger = logging.getLogger(__name__)
CALIBRATED_WEIGHTS_PATH = "config/calibrated_weights.json"

_DEFAULT_WEIGHTS: Dict[str, Dict[str, float]] = {
    "hard": {"rank": 5.0, "form": 20.0, "surface": 30.0, "elo": 0.15, "trj": 0.90},
    "clay": {"rank": 5.0, "form": 20.0, "surface": 35.0, "elo": 0.15, "trj": 0.90},
    "grass": {"rank": 5.0, "form": 18.0, "surface": 32.0, "elo": 0.18, "trj": 0.90},
}

_MIN_PROB = 0.02
_MAX_PROB = 0.98


def _is_calibration_healthy(entry: Dict[str, Any], as_of_date: Optional[str] = None) -> bool:
    """Vérifie qu'une calibration améliore le Brier Score et ne fuit pas le futur."""
    if entry.get("accepted") is False:
        return False
    b_before = entry.get("brier_before")
    b_after = entry.get("brier_after")
    if b_before is not None and b_after is not None:
        try:
            if float(b_after) > float(b_before):
                return False
        except (ValueError, TypeError):
            return False

    if as_of_date:
        trained_until = entry.get("trained_until")
        if not trained_until or str(trained_until) >= str(as_of_date):
            return False
    return True


def _load_surface_weights(
    surface: str, as_of_date: Optional[str] = None
) -> Dict[str, float]:
    bucket = normalize_surface(surface)
    if os.path.exists(CALIBRATED_WEIGHTS_PATH):
        try:
            with open(CALIBRATED_WEIGHTS_PATH, "r", encoding="utf-8") as f_in:
                data = json.load(f_in)
            entry = data.get(bucket)
            if isinstance(entry, dict):
                if _is_calibration_healthy(entry, as_of_date=as_of_date):
                    return {**_DEFAULT_WEIGHTS[bucket], **entry}
                if not as_of_date:
                    logger.warning(
                        "Calibration '%s' ignorée (Brier dégradé ou rejeté : %s -> %s), repli sur défauts.",
                        bucket,
                        entry.get("brier_before"),
                        entry.get("brier_after"),
                    )
        except (OSError, ValueError, TypeError):
            pass
    return dict(_DEFAULT_WEIGHTS[bucket])


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


def extract_scoring_components(match: MatchAnalysisData) -> Tuple[float, ...]:
    """Décompose un match en composantes linéaires exactes de compare_players().

    Retourne (fixed_a, fixed_b, rank_a, rank_b, form_a, form_b, surf_a, surf_b, elo_a, elo_b).
    """
    pa, pb = match.player_a, match.player_b
    h2h = match.h2h

    rank_a, rank_b = _score_diff(pb.ranking - pa.ranking, step=1.0, use_floor=True)

    form_parts = [
        _score_binary(pa.win_pct_last_10, pb.win_pct_last_10, 0.5),
        _score_binary(pa.win_pct_last_50, pb.win_pct_last_50, 1.0),
        _score_binary(pa.win_pct_1y, pb.win_pct_1y, 1.0),
        _score_binary(pa.win_pct_career, pb.win_pct_career, 1.0),
    ]
    form_a = sum(p[0] for p in form_parts)
    form_b = sum(p[1] for p in form_parts)

    surf_parts = [
        _score_binary(pa.win_pct_1y_surface, pb.win_pct_1y_surface, 2.0 / 3.0),
        _score_binary(pa.win_pct_career_surface, pb.win_pct_career_surface, 1.0),
    ]
    surf_a = sum(p[0] for p in surf_parts)
    surf_b = sum(p[1] for p in surf_parts)

    fixed_parts = [
        _score_diff(h2h.all_time[0] - h2h.all_time[1], step=1.0),
        _score_diff(h2h.last_year[0] - h2h.last_year[1], step=3.0),
        _score_diff(h2h.surface[0] - h2h.surface[1], step=5.0),
        _score_diff(h2h.games[0] - h2h.games[1], step=5.0),
        _score_binary(pa.matches_last_month, pb.matches_last_month, 10.0, invert=True),
        _score_binary(pa.tournament_minutes, pb.tournament_minutes, 10.0, invert=True),
        _score_binary(pa.first_serve_pct, pb.first_serve_pct, 20.0),
        _score_binary(pa.first_serve_pts_won, pb.first_serve_pts_won, 20.0),
        _score_binary(pa.break_points_saved_pct, pb.break_points_saved_pct, 20.0),
    ]
    fixed_a = sum(p[0] for p in fixed_parts) + pa.odds_spread * 5.0
    fixed_b = sum(p[1] for p in fixed_parts) + pb.odds_spread * 5.0

    elo_a = max(0.0, pa.elo - pb.elo) if (pa.elo > 0 and pb.elo > 0) else 0.0
    elo_b = max(0.0, pb.elo - pa.elo) if (pa.elo > 0 and pb.elo > 0) else 0.0

    return (fixed_a, fixed_b, rank_a, rank_b, form_a, form_b, surf_a, surf_b, elo_a, elo_b)


def _scores_to_prob_pair(score_a: float, score_b: float) -> Tuple[float, float]:
    safe_a = max(0.0, float(score_a))
    safe_b = max(0.0, float(score_b))
    total = safe_a + safe_b
    if total <= 0.0:
        return 0.5, 0.5
    prob_a = min(max(safe_a / total, _MIN_PROB), _MAX_PROB)
    return prob_a, 1.0 - prob_a


def _compute_odds_pair(
    score_a: float, score_b: float, trj: float = 0.90
) -> Tuple[float, float]:
    """Convertit deux scores en paire de cotes finies, positives et cohérentes avec le TRJ."""
    prob_a, prob_b = _scores_to_prob_pair(score_a, score_b)
    return round(trj / prob_a, 2), round(trj / prob_b, 2)


def compare_players(
    match: MatchAnalysisData,
    weights_override: Optional[Dict[str, float]] = None,
    as_of_date: Optional[str] = None,
) -> MatchAnalysisData:
    """Calcule les cotes théoriques sur MatchAnalysisData."""
    weights = (
        weights_override
        if weights_override is not None
        else _load_surface_weights(match.surface, as_of_date=as_of_date)
    )
    (
        fixed_a,
        fixed_b,
        rank_a,
        rank_b,
        form_a,
        form_b,
        surf_a,
        surf_b,
        elo_a,
        elo_b,
    ) = extract_scoring_components(match)

    score_a = (
        fixed_a
        + weights["rank"] * rank_a
        + weights["form"] * form_a
        + weights["surface"] * surf_a
        + weights["elo"] * elo_a
    )
    score_b = (
        fixed_b
        + weights["rank"] * rank_b
        + weights["form"] * form_b
        + weights["surface"] * surf_b
        + weights["elo"] * elo_b
    )
    match.player_a.model_odds, match.player_b.model_odds = _compute_odds_pair(
        score_a, score_b, trj=weights["trj"]
    )
    return match
