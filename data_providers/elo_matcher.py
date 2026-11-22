"""Extraction et appariement des classements ELO par surface."""

from itertools import takewhile
from typing import List, Tuple
import jaro
from core.player_extractor import PlayerExtractor

_MISSING_RATING_TOKENS = {"-", "—", "n/a", "na"}


class EloMatcher:
    """Recherche les notes ELO des joueurs dans les tables Tennis Abstract."""

    @staticmethod
    def _is_numeric(token: str) -> bool:
        try:
            float(token)
            return True
        except ValueError:
            return False

    @classmethod
    def _is_rating_slot(cls, token: str) -> bool:
        return cls._is_numeric(token) or token.strip().lower() in _MISSING_RATING_TOKENS

    @classmethod
    def get_player_elo(cls, player_line: str, match_player_name: str, surface: str) -> str:
        """Vérifie la correspondance du nom et extrait l'ELO de la surface."""
        if not player_line or not match_player_name or not match_player_name.strip():
            return ""

        words = player_line.strip().split()
        player_vs = " ".join(takewhile(lambda x: not cls._is_rating_slot(x), words))
        if not player_vs:
            return ""

        # Vérification stricte sur le nom de famille pour éviter les homonymes
        if player_vs.split()[-1].lower() != match_player_name.strip().split()[-1].lower():
            return ""

        alias_name = PlayerExtractor.PLAYER_ALIASES.get(
            match_player_name.strip(), match_player_name.strip()
        )
        sim_orig = jaro.jaro_winkler_metric(match_player_name.strip().lower(), player_vs.lower())
        sim_alias = jaro.jaro_winkler_metric(alias_name.lower(), player_vs.lower())
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
        lines = elo_data.splitlines()
        elo_a = cls._find_rating_for_player(lines, player_a_name, surface)
        elo_b = cls._find_rating_for_player(lines, player_b_name, surface)
        return elo_a, elo_b

    @classmethod
    def extract_elo_rating(cls, player_line: str, player_name: str, surface: str) -> str:
        """Extrait la valeur numérique ELO correspondant à la surface (Hard, Clay, Grass)."""
        stripped = player_line.strip()
        if not stripped:
            return ""

        clean_name = (player_name or "").strip()
        if clean_name and stripped.lower().startswith(clean_name.lower()):
            rating_tokens = stripped[len(clean_name):].strip().split()
        else:
            words = stripped.split()
            name_len = len(list(takewhile(lambda x: not cls._is_rating_slot(x), words)))
            rating_tokens = words[name_len:]

        if len(rating_tokens) < 3:
            return ""

        # Format Tennis Abstract (elo_finder.py) : [Hard, Clay, Grass]
        surf_low = (surface or "").strip().lower()
        if "clay" in surf_low:
            idx = 1
        elif "grass" in surf_low:
            idx = 2
        else:
            idx = 0

        candidate = rating_tokens[idx]
        return candidate if cls._is_numeric(candidate) else ""
