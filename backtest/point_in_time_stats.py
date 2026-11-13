"""Calculateur chronologiquement pur (zéro look-ahead bias) des stats et de l'ELO."""

from bisect import bisect_left
from datetime import timedelta
from typing import Dict, List, Tuple
import pandas as pd

INITIAL_ELO = 1500.0
ELO_K_FACTOR = 32.0


def _normalize_surface(surface: str) -> str:
    s_low = surface.strip().lower()
    if "clay" in s_low:
        return "clay"
    if "grass" in s_low:
        return "grass"
    return "hard"


def _expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


class PointInTimeStats:
    """Maintient l'historique et l'ELO glissant par surface avant chaque match."""

    def __init__(self, matches_df: pd.DataFrame) -> None:
        self.player_history: Dict[str, List[Tuple[pd.Timestamp, str, bool]]] = {}
        self.player_dates: Dict[str, List[pd.Timestamp]] = {}
        # Historique ELO : player -> surface -> List[(date, elo_avant_match)]
        self.elo_history: Dict[str, Dict[str, List[Tuple[pd.Timestamp, float]]]] = {}
        self.elo_dates: Dict[str, Dict[str, List[pd.Timestamp]]] = {}
        self._build_index(matches_df)

    def _record_elo_snapshot(
        self, player: str, surf: str, match_date: pd.Timestamp, rating: float
    ) -> None:
        self.elo_history.setdefault(player, {}).setdefault(surf, []).append((match_date, rating))
        self.elo_dates.setdefault(player, {}).setdefault(surf, []).append(match_date)

    def _build_index(self, matches_df: pd.DataFrame) -> None:
        if matches_df.empty:
            return
        df_sorted = matches_df.copy()
        df_sorted["Date"] = pd.to_datetime(df_sorted["Date"])
        df_sorted.sort_values("Date", inplace=True)

        current_elo: Dict[Tuple[str, str], float] = {}

        for _, row in df_sorted.iterrows():
            match_date = row["Date"]
            surf_raw = str(row.get("Surface", "")).strip().lower()
            surf_key = _normalize_surface(surf_raw)
            winner = str(row.get("Winner", "")).strip().lower()
            loser = str(row.get("Loser", "")).strip().lower()

            if winner:
                self.player_history.setdefault(winner, []).append((match_date, surf_raw, True))
            if loser:
                self.player_history.setdefault(loser, []).append((match_date, surf_raw, False))

            if winner and loser:
                elo_w = current_elo.get((winner, surf_key), INITIAL_ELO)
                elo_l = current_elo.get((loser, surf_key), INITIAL_ELO)
                self._record_elo_snapshot(winner, surf_key, match_date, elo_w)
                self._record_elo_snapshot(loser, surf_key, match_date, elo_l)

                exp_w = _expected_score(elo_w, elo_l)
                current_elo[(winner, surf_key)] = round(elo_w + ELO_K_FACTOR * (1.0 - exp_w), 1)
                current_elo[(loser, surf_key)] = round(elo_l + ELO_K_FACTOR * (0.0 - (1.0 - exp_w)), 1)

        for player, entries in self.player_history.items():
            self.player_dates[player] = [item[0] for item in entries]

    def get_player_elo_before(
        self, player_name: str, match_date: pd.Timestamp, surface: str
    ) -> float:
        """Retourne l'ELO du joueur sur la surface strictement avant match_date."""
        p_clean = player_name.strip().lower()
        surf_key = _normalize_surface(surface)
        dates = self.elo_dates.get(p_clean, {}).get(surf_key, [])
        if not dates:
            return INITIAL_ELO

        idx = bisect_left(dates, match_date)
        snapshots = self.elo_history[p_clean][surf_key]
        if idx < len(snapshots) and snapshots[idx][0] == match_date:
            return snapshots[idx][1]
        if idx > 0:
            # Recalcule l'ELO après le dernier match joué avant match_date
            return snapshots[idx - 1][1]
        return INITIAL_ELO

    @staticmethod
    def _tally_slice(
        history: List[Tuple[pd.Timestamp, str, bool]],
        end_idx: int,
        date_12m: pd.Timestamp,
        surf_clean: str,
    ) -> Tuple[int, int, int, int]:
        w_12m, tot_12m = 0, 0
        w_surf, tot_surf = 0, 0
        for idx in range(end_idx):
            m_date, m_surf, is_win = history[idx]
            if m_date >= date_12m:
                tot_12m += 1
                w_12m += int(is_win)
            if m_surf == surf_clean:
                tot_surf += 1
                w_surf += int(is_win)
        return w_12m, tot_12m, w_surf, tot_surf

    def get_player_stats_before(
        self, player_name: str, match_date: pd.Timestamp, surface: str
    ) -> Tuple[float, float, int]:
        """Calcule (% victoires 12 mois, % surface, nb matchs 12 mois) avant match_date."""
        p_clean = player_name.strip().lower()
        history = self.player_history.get(p_clean, [])
        if not history:
            return 50.0, 50.0, 0

        end_idx = bisect_left(self.player_dates[p_clean], match_date)
        if end_idx == 0:
            return 50.0, 50.0, 0

        date_12m = match_date - timedelta(days=365)
        surf_clean = surface.strip().lower()
        w_12m, tot_12m, w_surf, tot_surf = self._tally_slice(
            history, end_idx, date_12m, surf_clean
        )

        pct_12m = round((w_12m / tot_12m) * 100, 2) if tot_12m > 0 else 50.0
        pct_surf = round((w_surf / tot_surf) * 100, 2) if tot_surf > 0 else 50.0
        return pct_12m, pct_surf, tot_12m