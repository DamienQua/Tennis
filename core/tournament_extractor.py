"""Extraction des métadonnées du tournoi, de la surface et des classements."""

import re
from typing import List, Sequence, Tuple
from bs4 import BeautifulSoup
import jaro
import numpy as np


class TournamentExtractor:
    """Extrait le tournoi, la surface, le classement mondial et le favori."""

    @staticmethod
    def extract_tournament_slug(match_url: str) -> str:
        """Extrait le slug du tournoi depuis l'URL du match."""
        found = re.search(r"/\d{4}-([^/]+)/", match_url)
        if found:
            return found.group(1)
        parts = [part for part in match_url.split("/") if part]
        return parts[-2] if len(parts) >= 2 else match_url

    @staticmethod
    def _infer_surface_from_text(text: str) -> str:
        low = text.lower()
        if "indoor" in low:
            return "Indoor Hard"
        if "grass" in low:
            return "Grass"
        if "clay" in low:
            return "Clay"
        return "Hard"

    @classmethod
    def determine_tournament_and_surface(
        cls, match_url: str, tournaments: Sequence[str]
    ) -> Tuple[str, str]:
        """Détermine le nom du tournoi et la surface."""
        slug = cls.extract_tournament_slug(match_url)
        if tournaments is not None and len(tournaments) > 0:
            t_list = list(tournaments)
            scores = np.array(
                [jaro.jaro_winkler_metric(slug, t.split(" (")[0].lower()) for t in t_list],
                dtype=float,
            )
            tour_str = t_list[int(scores.argmax())]
            tour = tour_str.split(" (")[0]
            if "- " in tour_str:
                surface = tour_str.split("- ")[1].split(" Court")[0].strip()
            else:
                surface = cls._infer_surface_from_text(tour_str)
            return tour, surface
        clean_tour = slug.replace("-", " ").title()
        return clean_tour, cls._infer_surface_from_text(clean_tour)

    @staticmethod
    def parse_player_rankings(data: BeautifulSoup) -> List[int]:
        """Extrait les classements ATP/WTA des deux joueurs."""
        rankings: List[int] = []
        clean_txt = data.text.replace("Unknown", "1000")
        for idx in range(2):
            try:
                ranking = int(clean_txt.split("(HI")[idx].split("\n")[-1].strip())
            except (ValueError, IndexError, AttributeError):
                ranking = 1000
            rankings.append(ranking)
        return rankings

    @staticmethod
    def who_is_favorite(data: BeautifulSoup) -> List[int]:
        """Identifie le joueur favori selon le panneau bio."""
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