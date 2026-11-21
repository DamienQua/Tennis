"""Indexed Elo lookup for full names and unambiguous archive abbreviations.

The caller owns the date of the supplied table; this class does not turn current
ratings into historical ratings. Missing or ambiguous entries use the neutral
1500 baseline expected by legacy callers.
"""

from typing import Dict, Tuple

from data_providers.elo_matcher import get_elo_index, surface_index
from utils.player_identity import canonical_name


class FastEloMatcher:
    """Share the production table index without fuzzy surname matching."""

    def __init__(self, elo_text: str):
        self.exact_lookup = get_elo_index(elo_text)
        self._abbreviations: Dict[Tuple[str, str], set] = {}
        self.cache: Dict[Tuple[str, str], float] = {}
        for name in self.exact_lookup:
            parts = name.split()
            for split in range(1, len(parts)):
                surname = " ".join(parts[split:])
                initials = "".join(part[0] for part in parts[:split])
                for initial in (initials, initials[0]):
                    self._abbreviations.setdefault((surname, initial), set()).add(name)

    def get_elo(self, player_archive_name: str, surface: str) -> float:
        """Read the supplied table, preserving the documented neutral fallback."""
        cache_key = (player_archive_name, surface)
        if cache_key not in self.cache:
            self.cache[cache_key] = self._lookup_rating(player_archive_name, surface)
        return self.cache[cache_key]

    def _lookup_rating(self, player_name: str, surface: str) -> float:
        index = surface_index(surface)
        if index is None:
            return 1500.0
        name = canonical_name(player_name)
        if name not in self.exact_lookup:
            parts = name.split()
            split = len(parts)
            while split > 0 and len(parts[split - 1]) == 1:
                split -= 1
            candidates = self._abbreviations.get(
                (" ".join(parts[:split]), "".join(parts[split:])), set()
            )
            if len(candidates) != 1:
                return 1500.0
            name = next(iter(candidates))
        values = self.exact_lookup.get(name)
        return float(values[index]) if values and values[index] else 1500.0
