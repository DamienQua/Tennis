"""
Tennis match analysis module for coordinating recent matches, activity, and statistics.

Key classes:
- TennisMatchAnalyzer: Coordinates match analysis, win percentages, and odds spreads
- last_matchs: Main entry point function for analyzing player recent match history
"""

import asyncio
from typing import Any, List, Optional

import aiohttp
from bs4 import BeautifulSoup

from analysis.match_statistics_processor import MatchStatisticsProcessor
from analysis.tennis_data_fetcher import TennisDataFetcher
from analysis.tennis_data_parser import StatisticsProcessor, TennisDataParser
from utils.helpers import DateHelper, get_arg


class TennisMatchAnalyzer:
    """Coordinates data fetching, parsing, and analysis for previewed tennis matches."""

    def __init__(self, session: aiohttp.ClientSession, admin_url: Optional[str] = None):
        self.data_fetcher = TennisDataFetcher(session, admin_url)
        self.stats_processor = StatisticsProcessor()
        self.match_statistics_processor = MatchStatisticsProcessor(
            self.data_fetcher, self.stats_processor
        )

    @staticmethod
    def _get_odds_table_tokens(odds_spread: Optional[BeautifulSoup]) -> Optional[List[str]]:
        try:
            if not odds_spread:
                return None
            table = odds_spread.find(class_="stats-table")
            rows = table.find_all("tr") if table else []
            tds = rows[2].find_all("td") if len(rows) > 2 else []
            return tds[1].text.strip().split() if len(tds) > 1 else None
        except (AttributeError, IndexError):
            return None

    @staticmethod
    def _extract_odds_spread_value(
            odds_spread: Optional[BeautifulSoup], is_favorite: bool
    ) -> Optional[float]:
        odds_data = TennisMatchAnalyzer._get_odds_table_tokens(odds_spread)
        if not odds_data:
            return None
        odds_index = 2 if is_favorite else 0
        if len(odds_data) > odds_index:
            val = float(odds_data[odds_index])
            return -val if is_favorite else val
        return None

    async def _update_player_odds(
            self, match_vs, player_id: str, match_id: str, last_flag: int, favorite: Any
    ) -> None:
        try:
            odds_spread = await self.data_fetcher.fetch_player_activity_with_odds(
                player_id, match_id, 1, last_flag, favorite
            )
            is_fav = favorite[last_flag] == 1
            odds_val = self._extract_odds_spread_value(odds_spread, is_fav)
            if odds_val is not None:
                match_vs[42 + last_flag] = odds_val
        except (
            aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError, IndexError
        ):
            pass

    async def _fetch_match_context(self, match_id: str, player_id: str, default_tour: str):
        """Fetches tournament context and player activity datasets."""
        gathered = await asyncio.gather(
            self.fetch_tournament_data(match_id, default_tour=default_tour),
            self.data_fetcher.fetch_player_activities(player_id, match_id)
        )
        return gathered[0], gathered[1][0], gathered[1][1]

    async def analyze_match(self, *args, **kwargs):
        """Performs match analysis and updates match vector for given player."""
        today = get_arg(args, 0, kwargs.get("today"))
        match_vs = get_arg(args, 1, kwargs.get("match_vs"))
        player_id = get_arg(args, 2, kwargs.get("player_id"))
        match_id = get_arg(args, 3, kwargs.get("match_id"))
        last_flag = get_arg(args, 4, kwargs.get("last_flag", 0))
        favorite = get_arg(args, 5, kwargs.get("favorite", False))
        def_tour = match_vs[0] if len(match_vs) > 0 and match_vs[0] else ""

        tour_now, act1, surf = await self._fetch_match_context(match_id, player_id, def_tour)
        win_percentages = self.extract_win_percentages(act1, surf)
        match_stats = await self.match_statistics_processor.process_match_statistics(
            player_id, match_id, tour_now, activity_data=act1
        )
        nb_matches = self.calculate_matches_last_month(today, act1)

        self.update_match_vs(
            match_vs, win_percentages, match_stats, nb_matches, last_flag
        )
        await self._update_player_odds(match_vs, player_id, match_id, last_flag, favorite)

        return match_vs

    async def fetch_tournament_data(self, match_id: str, default_tour: str = "") -> str:
        """Delegates fetching tournament metadata to data fetcher."""
        return await self.data_fetcher.fetch_tournament_data(match_id, default_tour=default_tour)

    def extract_win_percentages(
            self, data_act1: Optional[BeautifulSoup], data_surf: Optional[BeautifulSoup]
    ) -> List[float]:
        """Extracts win percentages from activity and surface data."""
        raw_all = self.stats_processor.calculate_win_percentages(data_act1)
        all_percentages = (list(raw_all) + [0.0] * 4)[:4]

        raw_surf = self.stats_processor.calculate_win_percentages(data_surf)
        surf_part = raw_surf[2:] if len(raw_surf) >= 3 else raw_surf
        surface_percentages = (list(surf_part) + [0.0] * 2)[:2]

        return all_percentages + surface_percentages

    async def calculate_win_percentages(self, player_id: str, match_id: str) -> List[float]:
        """Fetches player activity and computes surface win percentages."""
        data_act1, data_surf = await self.data_fetcher.fetch_player_activities(player_id, match_id)
        return self.extract_win_percentages(data_act1, data_surf)

    @staticmethod
    def calculate_matches_last_month(today: float, data: Optional[BeautifulSoup]) -> int:
        """Counts player matches played within the last 30 days."""
        try:
            activity_table = data.find(id="activity-table") if data else None
            if not activity_table:
                return 0
            show_class = activity_table.find_all(class_="show")
            return DateHelper.calculate_matches_last_month(show_class, today)
        except (AttributeError, ValueError, TypeError, IndexError):
            return 0

    @staticmethod
    def update_match_vs(
            match_vs, win_percentages, match_stats, nb_match_last_month: int, last_flag: int
    ) -> None:
        """Updates match vector slice with extracted statistics."""
        offset = 14 + 11 * last_flag
        win_pct_list = (list(win_percentages) + [0.0] * 6)[:6]
        stats_list = (list(match_stats) + [0.0] * 4)[:4]
        match_vs[offset:offset+11] = win_pct_list + [nb_match_last_month] + stats_list


async def last_matchs(*args, **kwargs):
    """Entry point for analyzing player recent match statistics."""
    session = get_arg(args, 0, kwargs.get("session"))
    today = get_arg(args, 1, kwargs.get("today"))
    match_vs = get_arg(args, 2, kwargs.get("match_vs"))
    admin_url = get_arg(args, 3, kwargs.get("admin_url"))
    player_id = get_arg(args, 4, kwargs.get("player_id"))
    match_id = get_arg(args, 5, kwargs.get("match_id"))
    last_flag = get_arg(args, 6, kwargs.get("last_flag", 0))
    favorite = get_arg(args, 7, kwargs.get("favorite", False))
    analyzer = TennisMatchAnalyzer(session, admin_url)
    return await analyzer.analyze_match(
        today, match_vs, player_id, match_id, last_flag, favorite
    )
