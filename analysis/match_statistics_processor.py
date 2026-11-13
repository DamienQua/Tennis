"""Agrégation parallèle des statistiques et minutes jouées dans le tournoi en cours."""

import asyncio
from typing import Any, List, Optional, Tuple
import aiohttp
from bs4 import BeautifulSoup


class MatchStatisticsProcessor:
    """Agrège les minutes et stats de service sur les tours précédents du tournoi."""

    def __init__(self, data_fetcher, stats_processor) -> None:
        self.data_fetcher = data_fetcher
        self.stats_processor = stats_processor

    async def process_match_statistics(
        self,
        player_id: str,
        match_id: str,
        tour_now: str,
        activity_data: Optional[BeautifulSoup] = None,
    ) -> Tuple[int, float, float, float]:
        """Récupère en parallèle les stats des matchs du tournoi en cours."""
        data = (
            activity_data
            if activity_data is not None
            else await self.data_fetcher.fetch_player_activity(player_id, match_id, 1)
        )
        matches_list = data.find_all(class_="activity-clickthroughs no-link") if data else []

        valid_indices: List[int] = []
        for idx, match_elem in enumerate(matches_list):
            if not self.is_match_in_tournament(match_elem, tour_now):
                break
            valid_indices.append(idx)

        if not valid_indices:
            return 0, 0.0, 0.0, 0.0

        results = await asyncio.gather(
            *(self.get_match_statistics(matches_list, idx) for idx in valid_indices)
        )

        min_tour, per_first, pts_first, per_bp = 0, 0.0, 0.0, 0.0
        for m_i, new_stats in zip(valid_indices, results):
            min_tour, per_first, pts_first, per_bp = self.update_statistics(
                new_stats, (min_tour, per_first, pts_first, per_bp), m_i, data
            )
        return min_tour, per_first, pts_first, per_bp

    @staticmethod
    def update_statistics(
        new_stats: Optional[Tuple[int, float, float, float]],
        current_stats: Tuple[int, float, float, float],
        m_i: int,
        data: Optional[BeautifulSoup],
    ) -> Tuple[int, float, float, float]:
        """Cumule les minutes et conserve les stats de service du dernier match."""
        min_tour, per_first, pts_first, per_bp = current_stats
        if new_stats:
            min_tour += new_stats[0]
            if m_i == 0 and data and "Qualifying" not in data.text:
                per_first, pts_first, per_bp = new_stats[1:]
        return min_tour, per_first, pts_first, per_bp

    @staticmethod
    def is_match_in_tournament(match_elem: Any, tour_now: str) -> bool:
        """Vérifie l'appartenance d'un match au tournoi actuel."""
        if not tour_now or not getattr(match_elem, "contents", None) or len(match_elem.contents) < 2:
            return False
        href = match_elem.contents[1].get("href", "") if hasattr(match_elem.contents[1], "get") else ""
        clean_tour = tour_now.lower().replace(" ", "-")
        tokens = [t for t in clean_tour.split("-") if len(t) >= 4]
        return clean_tour in href or (bool(tokens) and all(tok in href for tok in tokens[:2]))

    async def get_match_statistics(
        self, matches_list: List[Any], m_i: int
    ) -> Optional[Tuple[int, float, float, float]]:
        """Récupère les statistiques d'un match individuel de manière sécurisée."""
        try:
            return await self.stats_processor.process_match_statistics(
                self.data_fetcher, matches_list, m_i
            )
        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            IndexError,
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
        ):
            return None