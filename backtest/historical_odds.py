"""Fournisseur de cotes historiques Tennis-Data.co.uk avec indexation O(1)."""

import os
from typing import Any, Dict, List, Optional, Tuple
import jaro
import pandas as pd


class HistoricalOddsProvider:
    """Charge et indexe les cotes de clôture et résultats historiques."""

    def __init__(self, data_dir: str = "backtest/data") -> None:
        self.data_dir = data_dir
        self._cache: Dict[str, pd.DataFrame] = {}
        self._surname_index: Dict[str, Dict[str, List[int]]] = {}

    def _load_dataset(self, year: int, gender: str) -> pd.DataFrame:
        key = f"{gender.lower()}_{year}"
        if key in self._cache:
            return self._cache[key]

        filepath = os.path.join(self.data_dir, f"{key}.xlsx")
        if not os.path.exists(filepath):
            return pd.DataFrame()

        data_frame = pd.read_excel(filepath)
        data_frame["Winner_Clean"] = data_frame["Winner"].astype(str).str.strip().str.lower()
        data_frame["Loser_Clean"] = data_frame["Loser"].astype(str).str.strip().str.lower()
        self._cache[key] = data_frame
        self._build_surname_index(key, data_frame)
        return data_frame

    def _build_surname_index(self, key: str, data_frame: pd.DataFrame) -> None:
        index: Dict[str, List[int]] = {}
        for idx, row in data_frame.iterrows():
            for col in ("Winner_Clean", "Loser_Clean"):
                tokens = str(row[col]).replace(".", "").split()
                if tokens:
                    surname = tokens[0]
                    index.setdefault(surname, []).append(int(idx))
        self._surname_index[key] = index

    @staticmethod
    def _extract_surname_and_initial(raw_name: str) -> Tuple[str, str]:
        """Normalise 'Novak Djokovic' ou 'Djokovic N.' en (nom_famille, initiale)."""
        clean = raw_name.replace(".", "").replace("-", " ").strip().lower()
        parts = clean.split()
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        # Format Tennis-Data : 'djokovic n' (initiale en dernier)
        if len(parts[-1]) == 1:
            return " ".join(parts[:-1]), parts[-1]
        # Format standard : 'novak djokovic' (prénom en premier)
        return parts[-1], parts[0][0]

    @classmethod
    def _name_matches(cls, player_full_name: str, candidate_name: str) -> bool:
        """Vérifie la correspondance exacte du nom de famille et de l'initiale."""
        p_surname, p_init = cls._extract_surname_and_initial(player_full_name)
        c_surname, c_init = cls._extract_surname_and_initial(candidate_name)
        if not p_surname or not c_surname:
            return False

        if p_surname == c_surname and (not p_init or not c_init or p_init == c_init):
            return True

        p_clean = player_full_name.replace("-", " ").strip().lower()
        c_clean = candidate_name.replace(".", "").strip().lower()
        return jaro.jaro_winkler_metric(p_clean, c_clean) >= 0.88

    def _candidate_row_indices(
        self, key: str, data_frame: pd.DataFrame, player_a: str, player_b: str
    ) -> List[int]:
        index = self._surname_index.get(key, {})
        sur_a, _ = self._extract_surname_and_initial(player_a)
        sur_b, _ = self._extract_surname_and_initial(player_b)
        candidates = set(index.get(sur_a, [])) | set(index.get(sur_b, []))
        if candidates:
            return sorted(candidates)
        return list(range(len(data_frame)))

    def _find_match_row(
        self, key: str, data_frame: pd.DataFrame, player_a: str, player_b: str
    ) -> Optional[Tuple[pd.Series, bool]]:
        """Recherche un match entre player_a et player_b via l'index."""
        for idx in self._candidate_row_indices(key, data_frame, player_a, player_b):
            row = data_frame.iloc[idx]
            winner_name = str(row["Winner"])
            loser_name = str(row["Loser"])
            if self._name_matches(player_a, winner_name) and self._name_matches(player_b, loser_name):
                return row, True
            if self._name_matches(player_b, winner_name) and self._name_matches(player_a, loser_name):
                return row, False
        return None

    def get_match_odds(
        self, player_a: str, player_b: str, year: int, gender: str = "atp"
    ) -> Optional[Dict[str, Any]]:
        """Retourne les cotes de clôture et le vainqueur réel du match."""
        key = f"{gender.lower()}_{year}"
        data_frame = self._load_dataset(year, gender)
        if data_frame.empty:
            return None

        found = self._find_match_row(key, data_frame, player_a, player_b)
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
        odds_w: Dict[str, float] = {}
        odds_l: Dict[str, float] = {}
        for book in ("B365", "PS", "Avg"):
            win_odd, loss_odd = cls._extract_market_odds(row, book)
            k_name = book.lower()
            odds_w[k_name] = win_odd
            odds_l[k_name] = loss_odd

        return {
            "winner": player_a if a_is_winner else player_b,
            "loser": player_b if a_is_winner else player_a,
            "a_is_winner": a_is_winner,
            "tournament": str(row.get("Tournament", "")),
            "date": str(row.get("Date", "")),
            "odds_a": odds_w if a_is_winner else odds_l,
            "odds_b": odds_l if a_is_winner else odds_w,
        }