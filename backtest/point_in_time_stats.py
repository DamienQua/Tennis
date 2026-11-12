"""
Chronologically pure player statistics calculator (zero look-ahead bias) for tennis backtests.
"""

from datetime import timedelta
from typing import Dict, List, Tuple
import pandas as pd


class PointInTimeStats:
    """Maintains player match history and computes pre-match statistics."""

    def __init__(self, matches_df: pd.DataFrame):
        self.player_history: Dict[str, List[Tuple[pd.Timestamp, str, bool]]] = {}
        self._build_index(matches_df)

    def _build_index(self, matches_df: pd.DataFrame) -> None:
        for _, row in matches_df.iterrows():
            match_date = pd.to_datetime(row["Date"])
            surface_name = str(row.get("Surface", "")).strip().lower()
            winner_name = str(row.get("Winner", "")).strip().lower()
            loser_name = str(row.get("Loser", "")).strip().lower()
            if winner_name:
                if winner_name not in self.player_history:
                    self.player_history[winner_name] = []
                self.player_history[winner_name].append((match_date, surface_name, True))
            if loser_name:
                if loser_name not in self.player_history:
                    self.player_history[loser_name] = []
                self.player_history[loser_name].append((match_date, surface_name, False))

    @staticmethod
    def _tally_history(
            history: List[Tuple[pd.Timestamp, str, bool]],
            match_date: pd.Timestamp,
            date_12m: pd.Timestamp,
            surf_clean: str
    ) -> Tuple[int, int, int, int]:
        w_12m, tot_12m = 0, 0
        w_surf, tot_surf = 0, 0
        for m_date, m_surf, is_win in history:
            if m_date >= match_date:
                continue
            if m_date >= date_12m:
                tot_12m += 1
                w_12m += int(is_win)
            if m_surf == surf_clean:
                tot_surf += 1
                w_surf += int(is_win)
        return w_12m, tot_12m, w_surf, tot_surf

    def get_player_stats_before(
            self,
            player_name: str,
            match_date: pd.Timestamp,
            surface: str
    ) -> Tuple[float, float, int]:
        """Compute rolling 12-month win %, surface win %, and match count before match_date."""
        p_clean = player_name.strip().lower()
        history = self.player_history.get(p_clean, [])
        if not history:
            return 50.0, 50.0, 0

        date_12m = match_date - timedelta(days=365)
        surf_clean = surface.strip().lower()

        w_12m, tot_12m, w_surf, tot_surf = self._tally_history(
            history, match_date, date_12m, surf_clean
        )

        pct_12m = round((w_12m / tot_12m) * 100, 2) if tot_12m > 0 else 50.0
        pct_surf = round((w_surf / tot_surf) * 100, 2) if tot_surf > 0 else 50.0

        return pct_12m, pct_surf, tot_12m
