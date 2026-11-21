"""Extraction des trois ELO de surface et index réutilisable par table."""

from functools import lru_cache
import math
import re
from types import MappingProxyType
from typing import List, Mapping, Optional, Tuple

from utils.player_identity import canonical_name, names_match

Ratings = Tuple[str, str, str]


def surface_index(surface: str) -> Optional[int]:
    """Retourne la colonne hard/clay/grass, sans inventer une surface inconnue."""
    words = set(re.findall(r"[a-z]+", (surface or "").casefold()))
    indexes = [index for index, name in enumerate(("hard", "clay", "grass")) if name in words]
    return indexes[0] if len(indexes) == 1 else None


def _parse_line(player_line: str) -> Optional[Tuple[str, Ratings]]:
    parts = player_line.strip().rsplit(maxsplit=3)
    if len(parts) != 4 or not canonical_name(parts[0]):
        return None
    ratings = []
    for value in parts[1:]:
        if value in ("-", "—", "N/A"):
            ratings.append("")
            continue
        try:
            number = float(value)
        except ValueError:
            return None
        if not math.isfinite(number) or number <= 0:
            return None
        ratings.append(value)
    return parts[0], tuple(ratings)


@lru_cache(maxsize=8)
def get_elo_index(elo_data: str) -> Mapping[str, Optional[Ratings]]:
    """Index immuable mis en cache par contenu ; les identités ambiguës sont refusées."""
    indexed = {}
    for line in elo_data.splitlines():
        parsed = _parse_line(line)
        if parsed is None:
            continue
        player, ratings = parsed
        key = canonical_name(player)
        if key in indexed and indexed[key] != ratings:
            indexed[key] = None
        else:
            indexed[key] = ratings
    return MappingProxyType(indexed)


class EloMatcher:
    """Recherche exacte après normalisation des noms et alias explicites."""

    @classmethod
    def get_player_elo(cls, player_line: str, match_player_name: str, surface: str) -> str:
        parsed = _parse_line(player_line)
        index = surface_index(surface)
        if parsed is None or index is None or not names_match(parsed[0], match_player_name):
            return ""
        return parsed[1][index]

    @classmethod
    def _find_rating_for_player(cls, lines: List[str], player_name: str, surface: str) -> str:
        return cls.find_elo_ratings("\n".join(lines), player_name, "", surface)[0]

    @classmethod
    def find_elo_ratings(
        cls, elo_data: str, player_a_name: str, player_b_name: str, surface: str
    ) -> Tuple[str, str]:
        index = surface_index(surface)
        if index is None:
            return "", ""
        table = get_elo_index(elo_data)

        def rating(name: str) -> str:
            values = table.get(canonical_name(name))
            return values[index] if values else ""

        return rating(player_a_name), rating(player_b_name)

    @staticmethod
    def extract_elo_rating(player_line: str, player_name: str, surface: str) -> str:
        """Préserve l'API de lecture d'une ligne, sans décaler les colonnes manquantes."""
        return EloMatcher.get_player_elo(player_line, player_name, surface)
