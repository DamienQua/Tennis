"""Modèles de données typés pour l'analyse de matchs de tennis."""

from dataclasses import dataclass, field
from math import isfinite
from typing import List, Optional, Tuple


@dataclass
class PlayerStats:
    """Statistiques individuelles d'un joueur."""

    name: str = ""
    ranking: int = 1000
    elo: float = 0.0

    # Pourcentages de victoires
    win_pct_last_10: float = 0.0
    win_pct_last_50: float = 0.0
    win_pct_1y: float = 0.0
    win_pct_career: float = 0.0
    win_pct_1y_surface: float = 0.0
    win_pct_career_surface: float = 0.0

    # Activité récente & fatigue
    matches_last_month: int = 0
    tournament_minutes: Optional[int] = None

    # Service & retour
    first_serve_pct: Optional[float] = None
    first_serve_pts_won: Optional[float] = None
    break_points_saved_pct: Optional[float] = None

    # Cotes & modèles
    model_odds: float = 0.0
    book_odds: float = 0.0
    odds_spread: float = 0.0


@dataclass
class H2HMetrics:
    """Statistiques des confrontations directes (Head-to-Head)."""

    all_time: Tuple[float, float] = (0.0, 0.0)
    last_year: Tuple[float, float] = (0.0, 0.0)
    surface: Tuple[float, float] = (0.0, 0.0)
    games: Tuple[float, float] = (0.0, 0.0)


@dataclass
class ConfidenceMetrics:
    """Métriques de confiance (remplace indice_tab)."""

    motivation_a: float = 0.0
    surface_rank_a: float = 0.0
    motivation_b: float = 0.0
    surface_rank_b: float = 0.0
    h2h_surface_bonus_a: float = 0.0
    h2h_surface_bonus_b: float = 0.0

    tactical_pairs: List[Tuple[float, float]] = field(default_factory=list)
    tiebreak_pair: Tuple[float, float] = (0.0, 0.0)

    book_fav_bonus: Tuple[float, float] = (0.0, 0.0)
    model_fav_bonus: Tuple[float, float] = (0.0, 0.0)

    final_index: float = 1.0


@dataclass
class MatchAnalysisData:
    """Représentation complète d'un match analysé (remplace match_vs)."""

    match_url: str
    tournament: str = ""
    surface: str = "Hard"
    player_a: PlayerStats = field(default_factory=PlayerStats)
    player_b: PlayerStats = field(default_factory=PlayerStats)
    h2h: H2HMetrics = field(default_factory=H2HMetrics)
    confidence: ConfidenceMetrics = field(default_factory=ConfidenceMetrics)
    market_status: str = "unknown"
    odds_observed_at: str = ""
    scheduled_start: str = ""

    def is_complete(self) -> bool:
        """Une analyse sans prix vérifiable ou ELO doit pouvoir être réessayée."""
        players = (self.player_a, self.player_b)
        try:
            return self.market_status == "prematch" and all(
                bool(player.name.strip())
                and all(isfinite(value) and value > 1.0 for value in (
                    player.model_odds, player.book_odds, player.elo
                ))
                for player in players
            )
        except (AttributeError, TypeError, ValueError):
            return False

    def get_player(self, index: int) -> PlayerStats:
        """Retourne player_a (0) ou player_b (1)."""
        return self.player_a if index == 0 else self.player_b

    def to_summary_line(self) -> str:
        """Formate la ligne de sortie compatible avec Matchs.txt."""
        pa, pb = self.player_a, self.player_b
        fmt = lambda val: f"{val}" if val else ""
        fmt_odds = lambda val: f"{val:.2f}" if val else ""
        fields = [
            self.tournament,
            self.surface,
            pa.name,
            pb.name,
            fmt_odds(pa.model_odds),
            fmt_odds(pb.model_odds),
            fmt_odds(pa.book_odds),
            fmt_odds(pb.book_odds),
            fmt(pa.elo),
            fmt(pb.elo),
            f"{pa.win_pct_last_50}",
            f"{pb.win_pct_last_50}",
            f"{self.confidence.final_index}",
            f"{pa.win_pct_career_surface}",
            f"{pb.win_pct_career_surface}",
        ]
        return ", ".join(fields)
