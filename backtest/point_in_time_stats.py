"""Statistiques et ELO disponibles strictement avant la journée du match."""

from bisect import bisect_left
from collections import defaultdict
from datetime import timedelta
from typing import Dict, List, Tuple
import pandas as pd

from analysis.probability_model import surface_bucket

INITIAL_ELO = 1500.0
ELO_K_FACTOR = 32.0


def completed_matches(matches_df: pd.DataFrame) -> pd.DataFrame:
    """Retire résultats incomplets, dates/noms absents et doublons d'archives."""
    if matches_df.empty:
        return matches_df.copy()
    frame = matches_df.copy()
    if "Comment" in frame:
        frame = frame[frame["Comment"].astype(str).str.strip().str.casefold() == "completed"]
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["Date", "Winner", "Loser"])
    for field in ("Winner", "Loser"):
        frame[field] = frame[field].astype(str).str.strip()
        frame = frame[frame[field].ne("")]
    frame = frame[frame["Winner"].str.casefold() != frame["Loser"].str.casefold()]
    identity = [key for key in ("Circuit", "Date", "Winner", "Loser", "Surface", "Tournament", "Round") if key in frame]
    return frame.drop_duplicates(subset=identity).sort_values("Date", kind="stable").reset_index(drop=True)


def _expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


class PointInTimeStats:
    """Indexe les victoires et les ELO après journée ; aucun résultat du jour ne fuit."""

    def __init__(self, matches_df: pd.DataFrame) -> None:
        self.player_history: Dict[str, List[Tuple[pd.Timestamp, str, bool]]] = {}
        self.player_dates: Dict[str, List[pd.Timestamp]] = {}
        self.elo_history: Dict[str, Dict[str, List[Tuple[pd.Timestamp, float]]]] = {}
        self.elo_dates: Dict[str, Dict[str, List[pd.Timestamp]]] = {}
        self._win_prefix: Dict[str, List[int]] = {}
        self._surface_dates: dict = {}
        self._surface_wins: dict = {}
        self._build_index(completed_matches(matches_df))

    def _build_index(self, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        current_elo: Dict[Tuple[str, str], float] = {}
        for match_date, matches in frame.groupby("Date", sort=True):
            # Tous les matchs du même jour utilisent le classement de la veille.
            # Les archives n'ont pas d'heure fiable : les mises à jour sont simultanées.
            deltas: dict = defaultdict(float)
            for _, row in matches.iterrows():
                surf = surface_bucket(str(row.get("Surface", "Hard")))
                winner, loser = row["Winner"].casefold(), row["Loser"].casefold()
                for player, won in ((winner, True), (loser, False)):
                    self.player_history.setdefault(player, []).append((match_date, surf, won))
                key_w, key_l = (winner, surf), (loser, surf)
                expectation = _expected_score(
                    current_elo.get(key_w, INITIAL_ELO), current_elo.get(key_l, INITIAL_ELO)
                )
                change = ELO_K_FACTOR * (1.0 - expectation)
                deltas[key_w] += change
                deltas[key_l] -= change
            for (player, surf), change in deltas.items():
                rating = round(current_elo.get((player, surf), INITIAL_ELO) + change, 1)
                current_elo[(player, surf)] = rating
                self.elo_history.setdefault(player, {}).setdefault(surf, []).append((match_date, rating))
                self.elo_dates.setdefault(player, {}).setdefault(surf, []).append(match_date)

        for player, entries in self.player_history.items():
            self.player_dates[player] = [entry[0] for entry in entries]
            prefix = [0]
            for played, surf, won in entries:
                prefix.append(prefix[-1] + int(won))
                key = (player, surf)
                self._surface_dates.setdefault(key, []).append(played)
                surface_prefix = self._surface_wins.setdefault(key, [0])
                surface_prefix.append(surface_prefix[-1] + int(won))
            self._win_prefix[player] = prefix

    def get_player_elo_before(self, player_name: str, match_date: pd.Timestamp, surface: str) -> float:
        """Renvoie le dernier ELO après une journée strictement antérieure."""
        player, surf = player_name.strip().casefold(), surface_bucket(surface)
        dates = self.elo_dates.get(player, {}).get(surf, [])
        index = bisect_left(dates, pd.Timestamp(match_date).normalize())
        return self.elo_history[player][surf][index - 1][1] if index else INITIAL_ELO

    def get_player_stats_before(
        self, player_name: str, match_date: pd.Timestamp, surface: str
    ) -> Tuple[float, float, int]:
        """Forme 12 mois et carrière surface, en O(log n) via sommes cumulées."""
        player = player_name.strip().casefold()
        dates = self.player_dates.get(player, [])
        match_date = pd.Timestamp(match_date).normalize()
        end = bisect_left(dates, match_date)
        start = bisect_left(dates, match_date - timedelta(days=365))
        total = end - start
        prefix = self._win_prefix.get(player, [0])
        wins = prefix[end] - prefix[start]
        key = (player, surface_bucket(surface))
        surf_end = bisect_left(self._surface_dates.get(key, []), match_date)
        surf_wins = self._surface_wins.get(key, [0])[surf_end]
        return (
            100.0 * wins / total if total else float("nan"),
            100.0 * surf_wins / surf_end if surf_end else float("nan"),
            total,
        )
