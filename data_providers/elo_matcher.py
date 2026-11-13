"""Extraction et appariement des classements ELO par surface."""

from itertools import takewhile
from typing import List, Tuple
import jaro
from core.player_extractor import PlayerExtractor


class EloMatcher:
    """Recherche les notes ELO des joueurs dans les tables Tennis Abstract."""

    @classmethod
    def get_player_elo(cls, player_line: str, match_player_name: str, surface: str) -> str:
        """Vérifie la correspondance du nom et extrait l'ELO de la surface."""
        words = player_line.split(" ")
        is_num = lambda x: x.isdigit() or x.replace(".", "", 1).isdigit()
        player_vs = " ".join(takewhile(lambda x: not is_num(x), words))
        if not player_vs:
            return ""

        # Vérification stricte sur le nom de famille pour éviter les homonymes
        if player_vs.split()[-1].lower() != match_player_name.split()[-1].lower():
            return ""

        alias_name = PlayerExtractor.PLAYER_ALIASES.get(match_player_name, match_player_name)
        sim_orig = jaro.jaro_winkler_metric(match_player_name, player_vs)
        sim_alias = jaro.jaro_winkler_metric(alias_name, player_vs)
        if sim_orig >= 0.95 or sim_alias >= 0.95:
            return cls.extract_elo_rating(player_line, player_vs, surface)
        return ""

    @classmethod
    def _find_rating_for_player(
        cls, lines: List[str], player_name: str, surface: str
    ) -> str:
        for line in lines:
            rating = cls.get_player_elo(line, player_name, surface)
            if rating:
                return rating
        return ""

    @classmethod
    def find_elo_ratings(
        cls, elo_data: str, player_a_name: str, player_b_name: str, surface: str
    ) -> Tuple[str, str]:
        """Retourne le couple (elo_a, elo_b) pour la surface demandée."""
        lines = elo_data.split("\n")
        elo_a = cls._find_rating_for_player(lines, player_a_name, surface)
        elo_b = cls._find_rating_for_player(lines, player_b_name, surface)
        return elo_a, elo_b

    @staticmethod
    def extract_elo_rating(player_line: str, player_name: str, surface: str) -> str:
        """Extrait la valeur numérique ELO correspondant à la surface."""
        tokens = player_line.replace("-", " ").split()
        if not tokens:
            return ""
        if "Hard" not in surface and surface != "Clay":
            return tokens[-2] if len(tokens) >= 2 else ""
        offset = 1 if "Hard" in surface else 2
        base_idx = player_name.replace("-", " ").count(" ") + offset
        for idx in range(base_idx, len(tokens)):
            candidate = tokens[idx]
            if candidate.replace(".", "", 1).isdigit():
                return candidate
        return ""