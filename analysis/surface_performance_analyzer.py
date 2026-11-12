"""
    Analyzes surface performance statistics for a tennis match.

    This class fetches and processes match statistics to calculate a player's performance
    rank based on their win percentage on a specific surface type.

    Args:
        data_fetcher: An object responsible for fetching match data.
        admin_url: The URL for accessing match statistics.

    Methods:
        analyze(match_id, surface, flag): Calculates rank from surface win percentages.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup

class SurfacePerformanceAnalyzer:
    SURFACE_INDICES = {"Hard": 12, "Indoor Hard": 19, "Carpet": 26, "Clay": 33, "Grass": 40}
    _stats_cache = {}

    def __init__(self, data_fetcher, admin_url):
        self.data_fetcher = data_fetcher
        self.admin_url = admin_url

    async def fetch_statistics_html(self, match_id):
        if match_id in SurfacePerformanceAnalyzer._stats_cache:
            return SurfacePerformanceAnalyzer._stats_cache[match_id]
        pane_req = {"action": "lazyLoadPanes", "pane": "statistics", "matchID": match_id}
        html = await self.data_fetcher.fetch_data(self.admin_url, pane_req)
        SurfacePerformanceAnalyzer._stats_cache[match_id] = html
        return html

    @classmethod
    def _find_surface_index(cls, surface):
        idx = cls.SURFACE_INDICES.get(surface)
        if idx is not None:
            return idx
        for name, index in cls.SURFACE_INDICES.items():
            if name.lower() in surface.lower():
                return index
        return None

    @staticmethod
    def _extract_tds(data, flag):
        table_idx = 1 if flag == 0 else 4
        tables = data.find_all(class_="table match-preview-statistics-table")
        if len(tables) > table_idx:
            return tables[table_idx].find_all("td")
        return []

    @staticmethod
    def _calculate_surface_rank(tds, target_idx):
        win_sur = float(tds[target_idx].text.replace("%", "").replace("N/A", "0"))
        rank = 10
        for j in range(12, min(len(tds), 41), 7):
            val = float(tds[j].text.replace("%", "").replace("N/A", "0"))
            if win_sur > val:
                rank += 10
        return rank

    async def analyze(self, match_id, surface, flag):
        try:
            pane_req = {"action": "lazyLoadPanes", "pane": "statistics", "matchID": match_id}
            stats_html = await self.data_fetcher.fetch_data(self.admin_url, pane_req)
            target_idx = self._find_surface_index(surface)
            if target_idx is None:
                return 10
            tds = self._extract_tds(BeautifulSoup(stats_html, "lxml"), flag)
            if len(tds) <= target_idx:
                return 10
            return self._calculate_surface_rank(tds, target_idx)
        except (
            aiohttp.ClientError, asyncio.TimeoutError,
            IndexError, ValueError, AttributeError, KeyError
        ):
            return 10
