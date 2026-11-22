"""Calcul des statistiques Head-to-Head (H2H) entre deux joueurs."""

from datetime import datetime
import re
from typing import Tuple
import unicodedata
from core.models import H2HMetrics
from utils.helpers import parse_english_date


def _norm(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).strip().lower()


def _matches_player(winner: str, player_name: str) -> bool:
    w_norm = _norm(winner)
    p_norm = _norm(player_name)
    if not w_norm or not p_norm:
        return False
    if w_norm in p_norm or p_norm in w_norm:
        return True
    w_parts = w_norm.split()
    p_parts = p_norm.split()
    return bool(w_parts and p_parts and w_parts[-1] == p_parts[-1])


class DateUtils:
    """Parsing et validation des fenêtres temporelles pour le H2H."""

    @staticmethod
    def parse_date(date_str: str) -> float:
        """Convertit une date texte anglaise en timestamp (indépendant de la locale OS)."""
        try:
            return parse_english_date(date_str).timestamp()
        except (ValueError, AttributeError, TypeError):
            return 0.0

    @staticmethod
    def is_within_last_year(date_ms: float) -> bool:
        """Vérifie si l'horodatage date de moins d'un an."""
        today = datetime.now().timestamp()
        year_sec = 365.25 * 24 * 3600
        return (today - date_ms) <= year_sec


class PlayerH2H:
    """Compteurs H2H individuels."""

    def __init__(self) -> None:
        self.wins_all = 0
        self.wins_year = 0
        self.wins_surface = 0
        self.games = 0


class H2HStats:
    """Agrège les confrontations directes et génère H2HMetrics."""

    def __init__(self, player_a: str, player_b: str) -> None:
        self.player_a = player_a
        self.player_b = player_b
        self.p_a = PlayerH2H()
        self.p_b = PlayerH2H()
        self.h2h_nb = 0
        self.h2h_y = 0

    @property
    def win_a_sur(self) -> int:
        return self.p_a.wins_surface

    @property
    def win_b_sur(self) -> int:
        return self.p_b.wins_surface

    def update_stats(
        self, winner: str, date_ms: float, surface: str, score: str, current_surface: str
    ) -> None:
        """Met à jour les compteurs suite à une rencontre historique."""
        if not winner or not winner.strip():
            return
        if _matches_player(winner, self.player_a):
            self._record_win(self.p_a, date_ms, surface, score, current_surface, loser_idx=0)
        elif _matches_player(winner, self.player_b):
            self._record_win(self.p_b, date_ms, surface, score, current_surface, loser_idx=1)

    def _record_win(
        self,
        player_stats: PlayerH2H,
        date_ms: float,
        surface: str,
        score: str,
        current_surface: str,
        loser_idx: int,
    ) -> None:
        player_stats.wins_all += 1
        if DateUtils.is_within_last_year(date_ms):
            player_stats.wins_year += 1
            self.h2h_y += 1
        if current_surface and current_surface.lower() in (surface or "").lower():
            player_stats.wins_surface += 1
        self._update_game_stats(score, loser_idx)

    def _update_game_stats(self, score: str, loser_index: int) -> None:
        clean_score = re.sub(r"\([^)]*\)", "", score)
        for set_score in clean_score.split():
            parts = set_score.split("-")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                self.p_a.games += int(parts[loser_index])
                self.p_b.games += int(parts[1 - loser_index])

    def to_metrics(self) -> H2HMetrics:
        """Retourne les pourcentages H2H structurés."""
        return H2HMetrics(
            all_time=self._calc_pct(self.p_a.wins_all, self.p_b.wins_all),
            last_year=self._calc_pct(self.p_a.wins_year, self.p_b.wins_year),
            surface=self._calc_pct(self.p_a.wins_surface, self.p_b.wins_surface),
            games=self._calc_pct(self.p_a.games, self.p_b.games),
        )

    @staticmethod
    def _calc_pct(wins_a: int, wins_b: int) -> Tuple[float, float]:
        total = wins_a + wins_b
        if total <= 0:
            return (0.0, 0.0)
        return (round(100 * wins_a / total, 2), round(100 * wins_b / total, 2))
