"""
Fast indexed matcher for player ELO ratings across surfaces from Tennis Abstract data.
"""

from typing import Dict, List, Optional, Tuple
import jaro


class FastEloMatcher:
    """Fast indexed matcher for player ELO ratings."""

    def __init__(self, elo_text: str):
        self.exact_lookup: Dict[str, Tuple[float, float, float]] = {}
        self.raw_lines: List[Tuple[str, Tuple[float, float, float]]] = []
        self._parse(elo_text)
        self.cache: Dict[Tuple[str, str], float] = {}

    def _parse(self, elo_text: str) -> None:
        for line in elo_text.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            tokens = line_str.split()
            if len(tokens) < 4:
                continue
            try:
                hard = float(tokens[-3])
                clay = float(tokens[-2])
                grass = float(tokens[-1])
            except ValueError:
                continue

            name_tokens = tokens[:-3]
            full_name = " ".join(name_tokens).lower()
            first_name = name_tokens[0].lower()
            init = first_name[0]
            surname = " ".join(name_tokens[1:]).lower()
            last_word = name_tokens[-1].lower()

            ratings = (hard, clay, grass)
            self.raw_lines.append((full_name, ratings))
            self.exact_lookup[f"{last_word}_{init}"] = ratings
            if surname:
                self.exact_lookup[f"{surname}_{init}"] = ratings
                self.exact_lookup[f"{surname.replace('-', ' ')}_{init}"] = ratings

    def get_elo(self, player_archive_name: str, surface: str) -> float:
        """Returns historical Elo rating for player prior to match date."""
        cache_key = (player_archive_name, surface)
        if cache_key in self.cache:
            return self.cache[cache_key]

        rating = self._lookup_rating(player_archive_name, surface)
        self.cache[cache_key] = rating
        return rating

    def _lookup_rating(self, player_archive_name: str, surface: str) -> float:
        p_clean = player_archive_name.replace(".", "").strip().lower()
        parts = p_clean.split()
        if not parts:
            return 1500.0

        ratings = self._get_exact_ratings(parts)
        if ratings:
            return self._select_surface_rating(ratings, surface)

        return self._fuzzy_lookup_rating(p_clean, surface)

    def _get_exact_ratings(self, parts: List[str]) -> Optional[Tuple[float, float, float]]:
        if len(parts) < 2:
            return self.exact_lookup.get(f"{parts[0]}_")
        init = parts[-1][0]
        last_word = parts[-2]
        surname = " ".join(parts[:-1])
        return (
            self.exact_lookup.get(f"{last_word}_{init}")
            or self.exact_lookup.get(f"{surname}_{init}")
        )

    def _fuzzy_lookup_rating(self, p_clean: str, surface: str) -> float:
        for full_name, rating_tuple in self.raw_lines:
            if jaro.jaro_winkler_metric(p_clean, full_name) >= 0.85:
                return self._select_surface_rating(rating_tuple, surface)
        return 1500.0

    @staticmethod
    def _select_surface_rating(ratings: Tuple[float, float, float], surface: str) -> float:
        surf_lower = surface.lower()
        if "clay" in surf_lower:
            return ratings[1]
        if "grass" in surf_lower:
            return ratings[2]
        return ratings[0]
