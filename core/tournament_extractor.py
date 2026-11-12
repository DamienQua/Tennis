"""
Module for extracting tournament metadata, surface, and player rankings from match data.
"""

import re
from typing import Any, List, Optional, Tuple

from bs4 import BeautifulSoup
import jaro
import numpy as np


class TournamentExtractor:
    """Extracts tournament slug, surface, player rankings, and match favorite status."""

    @staticmethod
    def extract_tournament_slug(match_url: str) -> str:
        """Extracts tournament slug identifier from match URL."""
        found = re.search(r'/\d{4}-([^/]+)/', match_url)
        if found:
            return found.group(1)
        parts = [part for part in match_url.split("/") if part]
        return parts[-2] if len(parts) >= 2 else match_url

    @classmethod
    def determine_tournament_and_surface(
            cls, match: str, tournaments: Any
    ) -> Tuple[str, str]:
        """Determines tournament name and court surface from URL and metadata."""
        slug = cls.extract_tournament_slug(match)
        if tournaments is not None and len(tournaments) > 0:
            t_list = list(tournaments)
            same_tour = np.zeros(len(t_list), float)
            for idx, tourn in enumerate(t_list):
                same_tour[idx] = jaro.jaro_winkler_metric(slug, tourn.split(" (")[0].lower())
            best_idx = int(same_tour.argmax(0))
            tour_str = t_list[best_idx]
            tour = tour_str.split(" (")[0]
            surface = tour_str.split("- ")[1].split(" Court")[0] if "- " in tour_str else "Clay"
            return tour, surface
        clean_tour = slug.replace("-", " ").title()
        return clean_tour, "Clay"

    @staticmethod
    def parse_player_rankings(data: BeautifulSoup) -> List[int]:
        """Parses player ATP/WTA rankings from overview HTML."""
        rankings = []
        for idx in range(2):
            try:
                clean_txt = data.text.replace("Unknown", "1000")
                ranking = int(clean_txt.split("(HI")[idx].split("\n")[-1].strip())
            except (ValueError, IndexError, AttributeError):
                ranking = 1000
            rankings.append(ranking)
        return rankings

    @staticmethod
    def who_is_favorite(data: BeautifulSoup) -> List[int]:
        """Identifies favorite player based on odds."""
        try:
            left_val = float(data.find(class_="mp_bio_left").find_all("li")[-1].text.strip())
            right_val = float(data.find(class_="mp_bio_right").find_all("li")[-1].text.strip())
            return [1, 0] if left_val > right_val else [0, 1]
        except (ValueError, IndexError, AttributeError):
            return [0, 0]


extract_tournament_slug = TournamentExtractor.extract_tournament_slug
determine_tournament_and_surface = TournamentExtractor.determine_tournament_and_surface
parse_player_rankings = TournamentExtractor.parse_player_rankings
who_is_favorite = TournamentExtractor.who_is_favorite
