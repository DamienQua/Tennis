"""Calcul de l'indice de confiance final à partir de ConfidenceMetrics."""

from math import ceil
from core.models import MatchAnalysisData


def _ratio_to_index(comp_value: float, comp_total: float) -> float:
    if comp_total <= 0:
        return 1.0
    ratio = comp_value / comp_total
    if ratio < 0.25:
        return 0.5
    if ratio < 0.50:
        return 1.0
    if ratio < 0.75:
        return 2.0
    return 3.0


def compare_indice(match: MatchAnalysisData) -> float:
    """Met à jour et retourne confidence.final_index."""
    conf = match.confidence
    score_a, score_b = 0.0, 0.0

    fixed_pairs = [
        (conf.motivation_a, conf.motivation_b),
        (conf.surface_rank_a, conf.surface_rank_b),
        (conf.h2h_surface_bonus_a, conf.h2h_surface_bonus_b),
        conf.book_fav_bonus,
        conf.model_fav_bonus,
    ]
    for val_a, val_b in fixed_pairs:
        if val_a > val_b:
            score_a += 20
        elif val_a < val_b:
            score_b += 20

    for val_a, val_b in [*conf.tactical_pairs, conf.tiebreak_pair]:
        if val_a > val_b:
            score_a += 5 * ceil((val_a - val_b) / 10)
        elif val_a < val_b:
            score_b += 5 * ceil((val_b - val_a) / 10)

    total = score_a + score_b
    pa_odds, pb_odds = match.player_a.model_odds, match.player_b.model_odds

    if pa_odds < pb_odds:
        conf.final_index = _ratio_to_index(score_a, total)
    elif pa_odds > pb_odds:
        conf.final_index = _ratio_to_index(score_b, total)
    else:
        conf.final_index = 1.0

    return conf.final_index