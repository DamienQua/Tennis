"""Analyse de la forme récente, fatigue et performances selon les cotes."""

import asyncio
from typing import List, Optional, Sequence
import aiohttp
from bs4 import BeautifulSoup
from analysis.match_statistics_processor import MatchStatisticsProcessor
from analysis.tennis_data_fetcher import TennisDataFetcher
from analysis.tennis_data_parser import StatisticsProcessor
from core.models import MatchAnalysisData
from utils.helpers import DateHelper


class TennisMatchAnalyzer:
    """Coordonne la récupération et la mise à jour des stats récentes d'un joueur."""

    def __init__(self, session: aiohttp.ClientSession, admin_url: Optional[str] = None) -> None:
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

    @classmethod
    def _extract_odds_spread_value(
        cls, odds_spread: Optional[BeautifulSoup], is_favorite: bool
    ) -> Optional[float]:
        odds_data = cls._get_odds_table_tokens(odds_spread)
        if not odds_data:
            return None
        odds_index = 2 if is_favorite else 0
        if len(odds_data) > odds_index:
            val = float(odds_data[odds_index])
            return -val if is_favorite else val
        return None

    async def _update_player_odds(
        self,
        match: MatchAnalysisData,
        player_id: str,
        match_id: str,
        last_flag: int,
        favorite: Sequence[int],
    ) -> None:
        try:
            odds_spread = await self.data_fetcher.fetch_player_activity_with_odds(
                player_id, match_id, 1, last_flag, favorite
            )
            is_fav = favorite[last_flag] == 1
            odds_val = self._extract_odds_spread_value(odds_spread, is_fav)
            if odds_val is not None:
                match.get_player(last_flag).odds_spread = odds_val
        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            ValueError,
            TypeError,
            IndexError,
        ):
            pass

    async def _fetch_match_context(self, match_id: str, player_id: str, default_tour: str):
        tour_now, activities = await asyncio.gather(
            self.data_fetcher.fetch_tournament_data(match_id, default_tour=default_tour),
            self.data_fetcher.fetch_player_activities(player_id, match_id),
        )
        return tour_now, activities[0], activities[1]

    async def analyze_match(
        self,
        today: float,
        match: MatchAnalysisData,
        player_id: str,
        match_id: str,
        last_flag: int = 0,
        favorite: Sequence[int] = (0, 0),
    ) -> MatchAnalysisData:
        """Analyse l'activité récente et met à jour PlayerStats."""
        tour_now, act1, surf = await self._fetch_match_context(
            match_id, player_id, match.tournament
        )
        win_percentages = self.extract_win_percentages(act1, surf)
        match_stats = await self.match_statistics_processor.process_match_statistics(
            player_id, match_id, tour_now, activity_data=act1
        )
        nb_matches = self.calculate_matches_last_month(today, act1)

        player = match.get_player(last_flag)
        player.win_pct_last_10 = win_percentages[0]
        player.win_pct_last_50 = win_percentages[1]
        player.win_pct_1y = win_percentages[2]
        player.win_pct_career = win_percentages[3]
        player.win_pct_1y_surface = win_percentages[4]
        player.win_pct_career_surface = win_percentages[5]
        player.matches_last_month = nb_matches
        player.tournament_minutes = match_stats[0]
        player.first_serve_pct = match_stats[1]
        player.first_serve_pts_won = match_stats[2]
        player.break_points_saved_pct = match_stats[3]

        await self._update_player_odds(match, player_id, match_id, last_flag, favorite)
        return match

    def extract_win_percentages(
        self, data_act1: Optional[BeautifulSoup], data_surf: Optional[BeautifulSoup]
    ) -> List[float]:
        raw_all = self.stats_processor.calculate_win_percentages(data_act1)
        all_percentages = (list(raw_all) + [0.0] * 4)[:4]
        raw_surf = self.stats_processor.calculate_win_percentages(data_surf)
        surf_part = raw_surf[2:] if len(raw_surf) >= 3 else raw_surf
        surface_percentages = (list(surf_part) + [0.0] * 2)[:2]
        return all_percentages + surface_percentages

    @staticmethod
    def calculate_matches_last_month(today: float, data: Optional[BeautifulSoup]) -> int:
        try:
            activity_table = data.find(id="activity-table") if data else None
            if not activity_table:
                return 0
            show_class = activity_table.find_all(class_="show")
            return DateHelper.calculate_matches_last_month(show_class, today)
        except (AttributeError, ValueError, TypeError, IndexError):
            return 0


async def last_matchs(
    session: aiohttp.ClientSession,
    today: float,
    match: MatchAnalysisData,
    admin_url: str,
    player_id: str,
    match_id: str,
    last_flag: int = 0,
    favorite: Sequence[int] = (0, 0),
) -> MatchAnalysisData:
    """Point d'entrée typé pour l'analyse de l'activité récente d'un joueur."""
    analyzer = TennisMatchAnalyzer(session, admin_url)
    return await analyzer.analyze_match(
        today, match, player_id, match_id, last_flag, favorite
    )