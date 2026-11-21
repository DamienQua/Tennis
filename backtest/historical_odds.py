"""Local historical odds joined by both players, exact day and tournament."""

from math import isfinite
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from utils.player_identity import canonical_name


def _abbreviated_name(name: str) -> Optional[Tuple[str, str]]:
    tokens = canonical_name(name).split()
    initials = []
    while tokens and len(tokens[-1]) == 1:
        initials.insert(0, tokens.pop())
    return (" ".join(tokens), "".join(initials)) if tokens and initials else None


class HistoricalOddsProvider:
    """Reject incomplete identities and ambiguous archive matches."""

    def __init__(self, data_dir: str = "backtest/data") -> None:
        self.data_dir = data_dir
        self._cache: Dict[str, pd.DataFrame] = {}
        self._event_index: dict = {}

    def _load_dataset(self, year: int, gender: str) -> pd.DataFrame:
        key = f"{gender.lower()}_{year}"
        if key in self._cache:
            return self._cache[key]
        filepath = Path(self.data_dir) / f"{key}.xlsx"
        if not filepath.exists():
            return pd.DataFrame()
        frame = pd.read_excel(filepath)
        if not {"Date", "Tournament", "Winner", "Loser"}.issubset(frame.columns):
            return pd.DataFrame()
        if "Comment" in frame:
            frame = frame[frame["Comment"].astype(str).str.strip().str.casefold() == "completed"]
        frame = frame.copy().reset_index(drop=True)
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.normalize()
        index = {}
        for row_index, row in frame.iterrows():
            if pd.notna(row["Date"]) and pd.notna(row["Tournament"]):
                identity = (row["Date"], canonical_name(str(row["Tournament"])))
                index.setdefault(identity, []).append(row_index)
        self._event_index[key] = index
        self._cache[key] = frame
        return frame

    @staticmethod
    def _name_matches(player_full_name: str, candidate_name: str) -> bool:
        first, second = canonical_name(player_full_name), canonical_name(candidate_name)
        if not first or not second or len(first.split()) < 2 or len(second.split()) < 2:
            return False
        if first == second:
            return True
        first_short, second_short = _abbreviated_name(first), _abbreviated_name(second)
        if first_short and second_short:
            return first_short == second_short
        short = first_short or second_short
        full = second if first_short else first
        if short is None:
            return False
        surname, initials = short
        suffix = " " + surname
        if not full.endswith(suffix):
            return False
        forenames = full[:-len(suffix)].split()
        return "".join(part[0] for part in forenames) == initials

    def get_match_odds(
        self, player_a: str, player_b: str, year: int, gender: str = "atp", *,
        match_date: Optional[Any] = None, tournament: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """No name-only lookup: callers must provide the day and archive tournament."""
        if match_date is None or not tournament or gender.lower() not in {"atp", "wta"}:
            return None
        try:
            played = pd.Timestamp(match_date).normalize()
        except (ValueError, TypeError):
            return None
        if pd.isna(played) or played.year != year:
            return None
        key = f"{gender.lower()}_{year}"
        frame = self._load_dataset(year, gender)
        candidates = self._event_index.get(key, {}).get((played, canonical_name(tournament)), [])
        matches = []
        for index in candidates:
            row = frame.loc[index]
            direct = self._name_matches(player_a, str(row["Winner"])) and self._name_matches(player_b, str(row["Loser"]))
            reverse = self._name_matches(player_b, str(row["Winner"])) and self._name_matches(player_a, str(row["Loser"]))
            if direct and reverse:
                return None
            if direct or reverse:
                matches.append((row, direct))
        if len(matches) != 1:
            return None
        row, a_is_winner = matches[0]
        return self._format_odds_dict(row, player_a, player_b, a_is_winner)

    @staticmethod
    def _extract_market_odds(row: pd.Series, prefix: str) -> Tuple[float, float]:
        try:
            winner = float(row.get(f"{prefix}W", 0))
            loser = float(row.get(f"{prefix}L", 0))
        except (TypeError, ValueError):
            return 0.0, 0.0
        if not all(isfinite(odd) and odd > 1 for odd in (winner, loser)):
            return 0.0, 0.0
        return winner, loser

    @classmethod
    def _format_odds_dict(cls, row: pd.Series, player_a: str, player_b: str, a_is_winner: bool) -> Dict[str, Any]:
        odds_w, odds_l = {}, {}
        for book in ("B365", "PS", "Avg"):
            odds_w[book.lower()], odds_l[book.lower()] = cls._extract_market_odds(row, book)
        return {
            "winner": player_a if a_is_winner else player_b,
            "loser": player_b if a_is_winner else player_a,
            "a_is_winner": a_is_winner,
            "tournament": str(row["Tournament"]), "date": str(row["Date"]),
            "odds_a": odds_w if a_is_winner else odds_l,
            "odds_b": odds_l if a_is_winner else odds_w,
        }
