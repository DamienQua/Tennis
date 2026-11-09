"""
Module for matching and extracting player Elo ratings from Tennis Abstract reports.
"""

from itertools import takewhile
import jaro

class EloMatcher:
    """Matches player names and extracts surface-specific Elo ratings."""

    @staticmethod
    def get_player_elo(player_line, match_player_name, surface):
        player_vs = " ".join(takewhile(lambda x: not (x.isdigit() or x.replace(".", "", 1).isdigit()), player_line.split(" ")))
        if jaro.jaro_winkler_metric(match_player_name, player_vs) >= 0.95:
            return EloMatcher.extract_elo_rating(player_line, player_vs, surface)
        return ""

    @staticmethod
    def find_elo_ratings(elo_data, player_a_name, player_b_name, surface):
        lines = elo_data.split("\n")
        elo_a = next((EloMatcher.get_player_elo(p, player_a_name, surface) for p in lines if EloMatcher.get_player_elo(p, player_a_name, surface)), "")
        elo_b = next((EloMatcher.get_player_elo(p, player_b_name, surface) for p in lines if EloMatcher.get_player_elo(p, player_b_name, surface)), "")
        return elo_a, elo_b

    @staticmethod
    def extract_elo_rating(player_line, player_name, surface):
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
