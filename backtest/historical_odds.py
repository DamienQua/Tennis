"""Fournisseur de cotes historiques Tennis-Data.co.uk avec indexation O(1) et désambiguïsation."""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple
import jaro
import pandas as pd
from utils.helpers import normalize_text

logger = logging.getLogger(__name__)


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
        clean = normalize_text(raw_name).replace(".", "").replace("-", " ").strip()
        parts = clean.split()
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        if len(parts[-1]) == 1:
            return " ".join(parts[:-1]), parts[-1]
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

        p_clean = normalize_text(player_full_name).replace("-", " ")
        c_clean = normalize_text(candidate_name).replace(".", "")
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

    def _find_all_match_rows(
        self, key: str, data_frame: pd.DataFrame, player_a: str, player_b: str
    ) -> List[Tuple[pd.Series, bool]]:
        matches: List[Tuple[pd.Series, bool]] = []
        for idx in self._candidate_row_indices(key, data_frame, player_a, player_b):
            row = data_frame.iloc[idx]
            winner_name = str(row["Winner"])
            loser_name = str(row["Loser"])
            if self._name_matches(player_a, winner_name) and self._name_matches(player_b, loser_name):
                matches.append((row, True))
            elif self._name_matches(player_b, winner_name) and self._name_matches(player_a, loser_name):
                matches.append((row, False))
        return matches

    @staticmethod
    def _tournament_similarity(query_tour: str, row_tour: str) -> float:
        q_norm = normalize_text(query_tour)
        r_norm = normalize_text(row_tour)
        if not q_norm or not r_norm:
            return 0.0
        if q_norm in r_norm or r_norm in q_norm:
            return 1.0
        q_tokens = {tok for tok in q_norm.split() if len(tok) >= 3}
        r_tokens = {tok for tok in r_norm.split() if len(tok) >= 3}
        if q_tokens and r_tokens and (q_tokens & r_tokens):
            return 0.9
        return float(jaro.jaro_winkler_metric(q_norm, r_norm))

    @classmethod
    def _disambiguate_matches(
        cls,
        matches: List[Tuple[pd.Series, bool]],
        tournament: Optional[str],
        match_date: Optional[str],
        round_name: Optional[str],
    ) -> Optional[Tuple[pd.Series, bool]]:
        if len(matches) == 1:
            return matches[0]

        filtered = list(matches)
        if match_date:
            try:
                target_dt = pd.to_datetime(match_date)
                date_filtered = [
                    item
                    for item in filtered
                    if abs((pd.to_datetime(item[0].get("Date")) - target_dt).days) <= 3
                ]
                if date_filtered:
                    filtered = date_filtered
            except (ValueError, TypeError):
                pass

        if len(filtered) > 1 and tournament:
            scored = [
                (cls._tournament_similarity(tournament, str(item[0].get("Tournament", ""))), item)
                for item in filtered
            ]
            best_score = max(score for score, _ in scored)
            if best_score >= 0.75:
                filtered = [item for score, item in scored if score >= best_score - 0.05]

        if len(filtered) > 1 and round_name:
            r_low = normalize_text(round_name)
            round_filtered = [
                item
                for item in filtered
                if r_low and r_low in normalize_text(str(item[0].get("Round", "")))
            ]
            if round_filtered:
                filtered = round_filtered

        if len(filtered) == 1:
            return filtered[0]

        logger.warning(
            "Confrontation historique ambiguë (%d matchs correspondants pour tournament=%r, date=%r).",
            len(filtered),
            tournament,
            match_date,
        )
        return None

    def get_match_odds(
        self,
        player_a: str,
        player_b: str,
        year: int,
        gender: str = "atp",
        tournament: Optional[str] = None,
        match_date: Optional[str] = None,
        round_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retourne les cotes de clôture et le vainqueur réel, ou None si ambigu/introuvable."""
        key = f"{gender.lower()}_{year}"
        data_frame = self._load_dataset(year, gender)
        if data_frame.empty:
            return None

        matches = self._find_all_match_rows(key, data_frame, player_a, player_b)
        if not matches:
            return None

        found = self._disambiguate_matches(matches, tournament, match_date, round_name)
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
