"""Calcul de l'indice de confiance final (compatible ConfidenceMetrics et indice_tab)."""

from math import ceil
from typing import Any, List, Sequence
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
    """Compare les indices de confiance entre deux joueurs."""

    def __init__(self, source: Any) -> None:
        self.source = source
        self.comp: List[float] = [0.0, 0.0, 0.0]

    def compare_indices(self) -> List[float]:
        """Exécute la comparaison sur ConfidenceMetrics ou un tableau indice_tab."""
        if isinstance(self.source, ConfidenceMetrics):
            self._compare_metrics(self.source)
        else:
            self._compare_legacy_array(self.source)
        self.comp[2] = self.comp[0] + self.comp[1]
        return self.comp

    def _accumulate_fixed(self, pairs: Sequence[tuple]) -> None:
        for val_a, val_b in pairs:
            if val_a > val_b:
                self.comp[0] += 20
            elif val_a < val_b:
                self.comp[1] += 20

    def _accumulate_scaled(self, pairs: Sequence[tuple]) -> None:
        for val_a, val_b in pairs:
            if val_a > val_b:
                self.comp[0] += 5 * ceil((val_a - val_b) / 10)
            elif val_a < val_b:
                self.comp[1] += 5 * ceil((val_b - val_a) / 10)

    def _compare_metrics(self, conf: ConfidenceMetrics) -> None:
        fixed_pairs = [
            (conf.motivation_a, conf.motivation_b),
            (conf.surface_rank_a, conf.surface_rank_b),
            (conf.h2h_surface_bonus_a, conf.h2h_surface_bonus_b),
            conf.book_fav_bonus,
            conf.model_fav_bonus,
        ]
        self._accumulate_fixed(fixed_pairs)
        self._accumulate_scaled([*conf.tactical_pairs, conf.tiebreak_pair])

    def _compare_legacy_array(self, tab: Sequence[float]) -> None:
        fixed_pairs = [(tab[i], tab[i + 1]) for i in (0, 1, 4, 20, 22)]
        scaled_pairs = [(tab[i], tab[i + 1]) for i in (6, 8, 10, 12, 14, 16, 18)]
        self._accumulate_fixed(fixed_pairs)
        self._accumulate_scaled(scaled_pairs)


def calculate_indice_24(comp: Sequence[float], match_data: Any) -> float:
    """Calcule l'indice pondéré final à partir des scores comparatifs."""
    if isinstance(match_data, MatchAnalysisData):
        odds_a = match_data.player_a.model_odds
        odds_b = match_data.player_b.model_odds
    else:
        odds_a = float(match_data[36])
        odds_b = float(match_data[37])

    if odds_a < odds_b:
        return _ratio_to_index(comp[0], comp[2])
    if odds_a > odds_b:
        return _ratio_to_index(comp[1], comp[2])
    return 1.0


def compare_indice(target: Any, match_vs: Any = None) -> float:
    """Point d'entrée compatible MatchAnalysisData et (indice_tab, match_vs)."""
    if isinstance(target, MatchAnalysisData):
        comparator = IndiceComparator(target.confidence)
        comp = comparator.compare_indices()
        target.confidence.final_index = calculate_indice_24(comp, target)
        return target.confidence.final_index

    comparator = IndiceComparator(target)
    comp = comparator.compare_indices()
    target[24] = calculate_indice_24(comp, match_vs)
    return float(target[24])