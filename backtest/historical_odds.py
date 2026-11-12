"""
Historical odds provider for backtesting tennis matches.

Loads Tennis-Data.co.uk historical match archives and matches player names
and dates to retrieve closing odds and real match outcomes.
"""

import os
from typing import Optional, Dict, Any, Tuple
import pandas as pd
import jaro

class HistoricalOddsProvider:
    """Provides historical match odds and results for backtesting."""

    def __init__(self, data_dir: str = "backtest/data"):
        self.data_dir = data_dir
        self._cache: Dict[str, pd.DataFrame] = {}

    def _load_dataset(self, year: int, gender: str) -> pd.DataFrame:
        key = f"{gender.lower()}_{year}"
        if key in self._cache:
            return self._cache[key]

        filename = f"{gender.lower()}_{year}.xlsx"
        filepath = os.path.join(self.data_dir, filename)
        if not os.path.exists(filepath):
            return pd.DataFrame()

        data_frame = pd.read_excel(filepath)
        data_frame["Winner_Clean"] = data_frame["Winner"].astype(str).str.strip().str.lower()
        data_frame["Loser_Clean"] = data_frame["Loser"].astype(str).str.strip().str.lower()
        self._cache[key] = data_frame
        return data_frame

    @staticmethod
    def _name_matches(player_full_name: str, candidate_name: str) -> bool:
        """Check if full name (e.g. 'Novak Djokovic') matches archive name (e.g. 'Djokovic N.')."""
        c_clean = candidate_name.replace(".", "").strip().lower()
        p_clean = player_full_name.replace("-", " ").strip().lower()
        p_parts = p_clean.split()
        if not p_parts:
            return False

        last_name = p_parts[-1]
        first_initial = p_parts[0][0]

        if last_name in c_clean and first_initial in c_clean:
            return True

        return jaro.jaro_winkler_metric(p_clean, c_clean) >= 0.85

    def _find_match_row(
            self, data_frame: pd.DataFrame, player_a: str, player_b: str
    ) -> Optional[Tuple[pd.Series, bool]]:
        """Search DataFrame for a match between player_a and player_b.
        Returns (row, a_is_winner)."""
        for _, row in data_frame.iterrows():
            winner_name = str(row["Winner"])
            loser_name = str(row["Loser"])
            if (
                    self._name_matches(player_a, winner_name)
                    and self._name_matches(player_b, loser_name)
            ):
                return row, True
            if (
                    self._name_matches(player_b, winner_name)
                    and self._name_matches(player_a, loser_name)
            ):
                return row, False
        return None

    def get_match_odds(
            self,
            player_a: str,
            player_b: str,
            year: int,
            gender: str = "atp"
    ) -> Optional[Dict[str, Any]]:
        """Looks up closing historical betting odds for two players."""
        data_frame = self._load_dataset(year, gender)
        if data_frame.empty:
            return None

        found = self._find_match_row(data_frame, player_a, player_b)
        if not found:
            return None

        row, a_is_winner = found
        return self._format_odds_dict(row, player_a, player_b, a_is_winner)

    @staticmethod
    def _extract_market_odds(row: pd.Series, prefix: str) -> Tuple[float, float]:
        win_odd = float(row.get(f"{prefix}W", 0.0) or 0.0)
        loss_odd = float(row.get(f"{prefix}L", 0.0) or 0.0)
        return win_odd, loss_odd

    @classmethod
    def _format_odds_dict(
            cls, row: pd.Series, player_a: str, player_b: str, a_is_winner: bool
    ) -> Dict[str, Any]:
        odds_w = {}
        odds_l = {}
        for book in ("B365", "PS", "Avg"):
            win_odd, loss_odd = cls._extract_market_odds(row, book)
            key = book.lower()
            odds_w[key] = win_odd
            odds_l[key] = loss_odd

        odds_a = odds_w if a_is_winner else odds_l
        odds_b = odds_l if a_is_winner else odds_w

        return {
            "winner": player_a if a_is_winner else player_b,
            "loser": player_b if a_is_winner else player_a,
            "a_is_winner": a_is_winner,
            "tournament": str(row.get("Tournament", "")),
            "date": str(row.get("Date", "")),
            "odds_a": odds_a,
            "odds_b": odds_b
        }
