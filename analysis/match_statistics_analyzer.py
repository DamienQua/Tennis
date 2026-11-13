"""Extraction des statistiques tactiques (service, retour, tie-breaks)."""

import re
from typing import List, Tuple
from bs4 import BeautifulSoup


class MatchStatisticsAnalyzer:
    """Calcule les métriques tactiques à partir du HTML d'un match."""

    IDX_FIRST_SERVE = 12
    IDX_SECOND_SERVE = 15
    IDX_BP_SAVED = 18
    IDX_RET_FIRST = 24
    IDX_RET_SECOND = 27
    IDX_BP_CONVERTED = 30

    @classmethod
    def calculate_serve_return_stats(
        cls, stats_match: BeautifulSoup, flag: int
    ) -> List[float]:
        """Retourne les 12 métriques (6 paires J1/J2) de service et retour."""
        default_stats = [0.0] * 12
        if not stats_match:
            return default_stats
        try:
            offset_flag = 2 if flag == 1 else 0
            cols = stats_match.find_all(class_="col-xs-4")
            if len(cols) < cls.IDX_BP_CONVERTED + 1 + offset_flag:
                return default_stats

            def _val(offset: int) -> float:
                raw = cols[offset + offset_flag].text.strip().split("%")[0]
                return float(raw) if raw and raw != "N/A" else 0.0

            p_first = _val(cls.IDX_FIRST_SERVE)
            p_second = _val(cls.IDX_SECOND_SERVE)
            r_first = _val(cls.IDX_RET_FIRST)
            r_second = _val(cls.IDX_RET_SECOND)
            p_bp = _val(cls.IDX_BP_SAVED)
            r_bp = _val(cls.IDX_BP_CONVERTED)

            if flag == 0:
                return [
                    p_first, 100.0 - p_first, p_second, 100.0 - p_second,
                    r_first, 100.0 - r_first, r_second, 100.0 - r_second,
                    p_bp, 100.0 - p_bp, r_bp, 100.0 - r_bp,
                ]
            return [
                100.0 - p_first, p_first, 100.0 - p_second, p_second,
                100.0 - r_first, r_first, 100.0 - r_second, r_second,
                100.0 - p_bp, p_bp, 100.0 - r_bp, r_bp,
            ]
        except (IndexError, ValueError, AttributeError, TypeError):
            return default_stats

    def calculate_tiebreak_stats(self, stats_match: BeautifulSoup) -> Tuple[float, float]:
        """Calcule le pourcentage de tie-breaks remportés par chaque joueur."""
        if not stats_match:
            return 0.0, 0.0
        try:
            col_12 = stats_match.find_all(class_="col-xs-12")
            headers = col_12[0].find_all("h4") if col_12 else []
            if not headers:
                return 0.0, 0.0
            scores = re.sub(r"\([^)]*\)", "", headers[0].text.strip())
            if scores:
                tb_j1, tb_j2 = self.parse_tiebreak_scores(scores)
                total = tb_j1 + tb_j2
                if total > 0:
                    return (100.0 * tb_j1 / total, 100.0 * tb_j2 / total)
        except (IndexError, ValueError, AttributeError, TypeError):
            return 0.0, 0.0
        return 0.0, 0.0

    def parse_tiebreak_scores(self, scores: str) -> Tuple[int, int]:
        """Compte les tie-breaks gagnés dans la chaîne de score."""
        tb_j1, tb_j2 = 0, 0
        for score in scores.split():
            if self.is_tiebreak(score):
                tb_j1, tb_j2 = self.update_tiebreak_counts(score, tb_j1, tb_j2)
        return tb_j1, tb_j2

    @staticmethod
    def is_tiebreak(score: str) -> bool:
        """Vérifie si un set s'est joué au tie-break."""
        parts = score.split("-")
        return (
            len(parts) == 2
            and parts[0].isdigit()
            and parts[1].isdigit()
            and int(parts[0]) >= 6
            and int(parts[1]) >= 6
        )

    @staticmethod
    def update_tiebreak_counts(score: str, tb_j1: int, tb_j2: int) -> Tuple[int, int]:
        """Incrémente le compteur du vainqueur du tie-break."""
        parts = score.split("-")
        if len(parts) >= 2 and int(parts[0]) > int(parts[1]):
            return tb_j1 + 1, tb_j2
        return tb_j1, tb_j2 + 1