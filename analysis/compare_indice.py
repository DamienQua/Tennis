"""Calcul de l'indice de confiance final sur MatchAnalysisData."""

from math import ceil
from typing import List, Sequence, Tuple
from core.models import ConfidenceMetrics, MatchAnalysisData


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


class IndiceComparator:
    """Compare les métriques de confiance entre les deux joueurs."""

    def __init__(self, confidence: ConfidenceMetrics) -> None:
        self.confidence = confidence
        self.comp: List[float] = [0.0, 0.0, 0.0]

    def compare_indices(self) -> List[float]:
        """Calcule les scores comparatifs [J1, J2, total] depuis ConfidenceMetrics."""
        conf = self.confidence
        fixed_pairs = [
            (conf.motivation_a, conf.motivation_b),
            (conf.surface_rank_a, conf.surface_rank_b),
            (conf.h2h_surface_bonus_a, conf.h2h_surface_bonus_b),
            conf.book_fav_bonus,
            conf.model_fav_bonus,
        ]
        self._accumulate_fixed(fixed_pairs)
        self._accumulate_scaled([*conf.tactical_pairs, conf.tiebreak_pair])
        self.comp[2] = self.comp[0] + self.comp[1]
        return self.comp

    def _accumulate_fixed(self, pairs: Sequence[Tuple[float, float]]) -> None:
        for val_a, val_b in pairs:
            if val_a > val_b:
                self.comp[0] += 20.0
            elif val_a < val_b:
                self.comp[1] += 20.0

    def _accumulate_scaled(self, pairs: Sequence[Tuple[float, float]]) -> None:
        for val_a, val_b in pairs:
            if val_a > val_b:
                self.comp[0] += 5.0 * ceil((val_a - val_b) / 10.0)
            elif val_a < val_b:
                self.comp[1] += 5.0 * ceil((val_b - val_a) / 10.0)


def calculate_indice_24(comp: Sequence[float], match_data: MatchAnalysisData) -> float:
    """Calcule l'indice pondéré final à partir des scores comparatifs."""
    odds_a = match_data.player_a.model_odds
    odds_b = match_data.player_b.model_odds

    if odds_a < odds_b:
        return _ratio_to_index(comp[0], comp[2])
    if odds_a > odds_b:
        return _ratio_to_index(comp[1], comp[2])
    return 1.0


def compare_indice(match: MatchAnalysisData) -> float:
    """Calcule et enregistre confidence.final_index sur MatchAnalysisData."""
    comparator = IndiceComparator(match.confidence)
    comp = comparator.compare_indices()
    match.confidence.final_index = calculate_indice_24(comp, match)
    return match.confidence.final_index
