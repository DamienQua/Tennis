"""Calcul des statistiques Head-to-Head (H2H) entre deux joueurs."""

from datetime import datetime
import re
from typing import Tuple
from core.models import H2HMetrics
from utils.player_identity import canonical_name


class DateUtils:
    """Parsing et validation des fenêtres temporelles pour le H2H."""

    @staticmethod
    def parse_date(date_str: str) -> float:
        """Convertit une date texte en timestamp."""
        try:
            return datetime.strptime(date_str.strip(), "%b %d %Y").timestamp()
        except (ValueError, AttributeError):
            return 0.0

    @staticmethod
    def is_within_last_year(date_ms: float) -> bool:
        """Vérifie si l'horodatage date de moins d'un an."""
        today = datetime.now().timestamp()
        year_sec = 365.25 * 24 * 3600
        return 0 <= (today - date_ms) <= year_sec


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
    ) -> bool:
        """Met à jour les compteurs suite à une rencontre historique."""
        winner_index = self.winner_index(winner)
        if winner_index is None:
            return False
        if winner_index == 0:
            self._record_win(self.p_a, date_ms, surface, score, current_surface, loser_idx=0)
        else:
            self._record_win(self.p_b, date_ms, surface, score, current_surface, loser_idx=1)
        return True

    def winner_index(self, winner: str):
        """Résout une identité complète ou un nom court unique parmi les joueurs."""
        name = canonical_name(winner)
        if not name:
            return None
        players = [canonical_name(self.player_a), canonical_name(self.player_b)]
        matches = [index for index, player in enumerate(players) if name == player]
        if not matches and " " not in name:
            matches = [
                index for index, player in enumerate(players)
                if player and name == player.split()[-1]
            ]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def same_surface(first: str, second: str) -> bool:
        """Conserve la distinction dur extérieur / dur intérieur de la source."""
        def normalized(value: str) -> str:
            value = canonical_name(value).replace(" court", "")
            return value.removeprefix("outdoor ")

        return bool(first and second) and normalized(first) == normalized(second)

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
        if self.same_surface(current_surface, surface):
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
