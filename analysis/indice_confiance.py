"""
Tennis data analysis module for fetching and analyzing player and match data.

This module provides classes and functions for:
- Fetching tennis-related data asynchronously
- Analyzing player motivation based on recent match history
- Analyzing match tactics and performance
- Calculating confidence indices for tennis match predictions

The module supports different analysis types including:
- Motivation analysis
- Tactics analysis
- Surface performance analysis

Key components:
- TennisDataFetcher: Handles asynchronous data retrieval
- MotivationAnalyzer: Evaluates player motivation
- TacticsAnalyzer: Examines match statistics and tactics
- indice_confiance: Main function coordinating different analysis types
"""

import asyncio
from datetime import date

import aiohttp
from bs4 import BeautifulSoup

from analysis.last_matchs import TennisDataFetcher
from analysis.match_statistics_analyzer import MatchStatisticsAnalyzer
from analysis.surface_performance_analyzer import SurfacePerformanceAnalyzer
from utils.helpers import get_arg

class MotivationAnalyzer:
    """Analyzes player motivation by tracking tournament tiers and recent activity count."""

    def __init__(self, data_fetcher, admin_url, indice_tab):
        self.data_fetcher = data_fetcher
        self.admin_url = admin_url
        self.indice_tab = indice_tab
        self.surface_analyzer = SurfacePerformanceAnalyzer(data_fetcher, admin_url)

    async def analyze(self, player_id, match_id, surface, flag):
        """Executes tactical analysis on match URL and updates confidence indices."""
        data_html = await self.fetch_player_activity(player_id, match_id)
        data = BeautifulSoup(data_html, "lxml")

        cat = self.get_tournament_category(data)
        nb_matchs = self.count_matches(data)

        self.calculate_motivation_index(cat, nb_matchs, flag)

        await self.analyze_surface_performance(match_id, surface, flag)

    async def fetch_player_activity(self, player_id, match_id):
        """Fetches player activity pane HTML from admin URL."""
        player_param = {
            "action": "playerActivity",
            "activityOffset": "0",
            "basic-activity-option": "3",
            "odds": "0",
            "filterType": "basic",
            "playerID": player_id,
            "matchID": match_id
        }
        return await self.data_fetcher.fetch_data(self.admin_url, player_param)

    @staticmethod
    def get_tournament_category(data):
        """Extracts tournament tier or category from activity table."""
        try:
            table = data.find(id="activity-table") if data else None
            if table:
                subheaders = table.find_all(class_="subheader")
                if subheaders:
                    return subheaders[0].text
        except (AttributeError, IndexError):
            pass
        return "250"

    @staticmethod
    def _get_year_index(show_class, year):
        for idx, item in enumerate(show_class):
            if str(year) in item.text:
                return idx + 1
        return -1

    @staticmethod
    def _count_matches_in_year(show_class, start_index):
        count = 0
        for idx in range(start_index, len(show_class)):
            if show_class[idx].text == "Date":
                break
            count += 1
        return count

    def count_matches(self, data):
        """Counts matches played by player in current season."""
        try:
            table = data.find(id="activity-table") if data else None
            if not table:
                return -1
            show_class = table.find_all(class_="show")
            year = date.today().year
            start_index = self._get_year_index(show_class, year)
            if start_index == -1:
                return -1
            return self._count_matches_in_year(show_class, start_index)
        except (AttributeError, IndexError, TypeError):
            return -1

    def calculate_motivation_index(self, cat, nb_matchs, flag):
        """Calculates motivation index based on tier and match count."""
        index = 2 * flag
        thresholds = {
            "250": (0, 2),
            "500": (0, 2),
            "1000": (0, float('inf')),
            "Slam": (0, float('inf'))
        }
        matched = False
        for key, (low, high) in thresholds.items():
            if key in cat:
                if nb_matchs < 0:
                    self.indice_tab[index] = 0
                elif low <= nb_matchs < high:
                    self.indice_tab[index] = 50
                else:
                    self.indice_tab[index] = 100
                matched = True
                break
        if not matched:
                # Fallback for unknown categories (e.g. "WTA Ch"): same logic as 250/500
            if nb_matchs < 0:
                self.indice_tab[index] = 0
            elif nb_matchs < 2:
                self.indice_tab[index] = 50
            else:
                self.indice_tab[index] = 100

    async def analyze_surface_performance(self, match_id, surface, flag):
        """Analyzes surface performance rank and updates confidence indices."""
        self.indice_tab[2*flag+1] = await self.surface_analyzer.analyze(match_id, surface, flag)

class TacticsAnalyzer:
    """Analyzes tactical serving, returning, and tiebreak metrics from match stats."""

    def __init__(self, data_fetcher, admin_url, indice_tab):
        self.data_fetcher = data_fetcher
        self.admin_url = admin_url
        self.indice_tab = indice_tab
        self.stats_analyzer = MatchStatisticsAnalyzer()

    async def analyze(self, match_url, flag):
        """Analyzes tactical serve, return, and tiebreak metrics from match stats."""
        match_id = self.extract_match_id(match_url)
        stats_match = await self.fetch_match_stats(match_id)
        serve_return_stats = self.stats_analyzer.calculate_serve_return_stats(stats_match, flag)
        tiebreak_stats = self.stats_analyzer.calculate_tiebreak_stats(stats_match, flag)
        self.indice_tab[6:18] = serve_return_stats
        self.indice_tab[18:20] = tiebreak_stats

    @staticmethod
    def extract_match_id(match_url):
        """Extracts numeric match ID from match preview URL."""
        return match_url.split("match/")[1].split("/")[0]

    async def fetch_match_stats(self, match_id):
        """Fetches match statistics pane HTML for match ID."""
        req = {"action": "showMatchStats", "matchID": match_id, "refresh": "true"}
        stats_match_html = await self.data_fetcher.fetch_data(self.admin_url, req)
        return BeautifulSoup(stats_match_html, "lxml")

async def indice_confiance(*args, match_url="", indice_tab=None, **kwargs):
    """Main entry point for confidence index calculation across categories."""
    session = get_arg(args, 0, kwargs.get("session"))
    admin_url = get_arg(args, 1, kwargs.get("admin_url"))
    player_id = get_arg(args, 2, kwargs.get("player_id"))
    match_id = get_arg(args, 3, kwargs.get("match_id"))
    surface = get_arg(args, 4, kwargs.get("surface"))
    flag = get_arg(args, 5, kwargs.get("flag", 0))
    choix = get_arg(args, 6, kwargs.get("choix", ""))
    match_url = kwargs.get("match_url", get_arg(args, 7, match_url))
    indice_tab = kwargs.get("indice_tab", get_arg(args, 8, indice_tab))

    if indice_tab is None:
        from utils.variables import indice_tab as default_tab
        indice_tab = default_tab
    data_fetcher = TennisDataFetcher(session)

    if choix == "Motivation":
        motivation_analyzer = MotivationAnalyzer(data_fetcher, admin_url, indice_tab)
        await motivation_analyzer.analyze(player_id, match_id, surface, flag)

    elif choix == "Tactique":
        tactics_analyzer = TacticsAnalyzer(data_fetcher, admin_url, indice_tab)
        await tactics_analyzer.analyze(match_url, flag)

    elif choix == "Surface":
        surface_analyzer = SurfacePerformanceAnalyzer(data_fetcher, admin_url)
        indice_tab[2*flag+1] = await surface_analyzer.analyze(match_id, surface, flag)
    return indice_tab
