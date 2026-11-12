"""
Tennis match analysis module for fetching and processing player and match statistics.

This module provides classes and methods to:
- Fetch tennis match data from an admin URL
- Parse player activity and match statistics
- Calculate win percentages and match-related metrics
- Analyze match details for two players

Key classes:
- TennisDataFetcher: Handles async data retrieval from a tennis statistics source
- TennisDataParser: Parses raw match and player data
- StatisticsProcessor: Processes match statistics
- TennisMatchAnalyzer: Coordinates match analysis and data processing

The last_matchs function serves as the main entry point for match analysis.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from analysis.match_statistics_processor import MatchStatisticsProcessor
from utils.helpers import DateHelper, get_arg

class TennisDataFetcher:
    _activity_pane_cache = {}

    def __init__(self, session, admin_url=None):
        self.session = session
        self.admin_url = admin_url

    async def fetch_data(self, url, data=None, method='POST'):
        max_retries = 2
        for attempt in range(max_retries):
            try:
                if method.upper() == 'GET':
                    req = self.session.get(url)
                else:
                    req = self.session.post(url, data=data)
                async with req as response:
                    return await response.text()
            except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError):
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.0)
                else:
                    raise
        return ""

    @staticmethod
    def _extract_tournament_name(soup):
        for elem_id in ("basic-this-tournament-A", "basic-this-tournament-B"):
            elem = soup.find(id=elem_id)
            val = elem.get("value") if elem else ""
            if "At " in val:
                parts = val.split("At ")
                if len(parts) > 1 and parts[1].strip():
                    return parts[1].strip()
        return ""

    async def fetch_tournament_data(self, match_id, default_tour=""):
        try:
            if match_id not in TennisDataFetcher._activity_pane_cache:
                pane_req = {"action": "lazyLoadPanes", "pane": "activity", "matchID": match_id}
                TennisDataFetcher._activity_pane_cache[match_id] = await self.fetch_data(
                    self.admin_url, pane_req
                )
            soup = BeautifulSoup(TennisDataFetcher._activity_pane_cache[match_id], "lxml")
            tour_name = self._extract_tournament_name(soup)
            if tour_name:
                return tour_name
        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, AttributeError):
            pass
        return default_tour or ""

    async def fetch_player_activity(self, player_id, match_id, activity_option, odds_option = "0"):
        player_param = {
            "action": "playerActivity",
            "activityOffset": "0",
            "basic-activity-option": str(activity_option),
            "odds": str(odds_option),
            "filterType": "basic",
            "playerID": player_id,
            "matchID": match_id
        }
        data_html = await self.fetch_data(self.admin_url, player_param)
        return BeautifulSoup(data_html, "lxml")

    async def fetch_player_activities(self, player_id, match_id):
        return await asyncio.gather(
            self.fetch_player_activity(player_id, match_id, 1),
            self.fetch_player_activity(player_id, match_id, 2)
        )

    async def fetch_player_activity_with_odds(
        self, player_id, match_id, activity_option, flag, favorite
    ):
        odds_option = "5" if favorite[flag] == 1 else "6"
        return await self.fetch_player_activity(
            player_id, match_id, activity_option, odds_option
        )

    async def fetch_match_statistics(self, match_element):
        try:
            a_tags = match_element.find_all("a") if match_element else []
            valid_link = len(a_tags) >= 2 and a_tags[1].has_attr("data-action")
            if valid_link and a_tags[1].has_attr("data-matchid"):
                action_data = {
                    "action": a_tags[1]["data-action"],
                    "matchID": a_tags[1]["data-matchid"]
                }
                stats_match_html = await self.fetch_data(self.admin_url, action_data)
                return BeautifulSoup(stats_match_html, "lxml")
        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, AttributeError, IndexError):
            pass
        return None

class TennisDataParser:
    @staticmethod
    def _extract_single_percentage(percentage_str):
        try:
            cleaned = percentage_str.replace("N/A", "0").strip().replace("\t", "")
            parts = cleaned.split("\n\n")
            target = parts[1] if len(parts) > 1 else parts[0]
            val = target.replace("N/A", "0").strip().split("%")[0].strip()
            return float(val) if val else 0.0
        except (ValueError, IndexError, AttributeError):
            return 0.0

    @classmethod
    def parse_win_percentages(cls, data):
        if not data or not getattr(data, "text", None):
            return []
        text = data.text
        tl = text.lower()
        # Use case-insensitive position search but extract from original text to preserve "N/A"
        def split_after(marker):
            pos = tl.find(marker.lower())
            return [text[pos + len(marker):]] if pos >= 0 else []
        win_percentages = text.split("Matches")[1:3] + split_after("months)") + split_after("2000)")
        return [cls._extract_single_percentage(p) for p in win_percentages]

    @staticmethod
    def parse_match_statistics(stats_match):
        if not stats_match:
            return 0, 0, 0, 0
        try:
            h5 = stats_match.find("h5")
            min_tour = int(h5.text.split(" m")[0]) if h5 and " m" in h5.text else 0
            cols = stats_match.find_all(class_="col-xs-4")
            def _extract_pct(idx):
                if len(cols) <= idx:
                    return 0.0
                return float(cols[idx].text.replace("N/A", "0").strip().split("%")[0])

            per_first_serve = _extract_pct(9)
            points_first_serve = _extract_pct(12)
            per_save_bp = _extract_pct(18)
            return min_tour, per_first_serve, points_first_serve, per_save_bp
        except (IndexError, ValueError, AttributeError, TypeError):
            return 0, 0, 0, 0

class StatisticsProcessor:
    @staticmethod
    def calculate_win_percentages(data):
        return TennisDataParser.parse_win_percentages(data)

    @staticmethod
    async def process_match_statistics(data_fetcher, matches_list, m_i, *args, **kwargs):
        stats_match = await data_fetcher.fetch_match_statistics(matches_list[m_i])
        return TennisDataParser.parse_match_statistics(stats_match)

class TennisMatchAnalyzer:
    def __init__(self, session, admin_url):
        self.data_fetcher = TennisDataFetcher(session, admin_url)
        self.stats_processor = StatisticsProcessor()
        self.match_statistics_processor = MatchStatisticsProcessor(
            self.data_fetcher, self.stats_processor
        )

    @staticmethod
    def _get_odds_table_tokens(odds_spread):
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
    def _extract_odds_spread_value(odds_spread, is_favorite):
        odds_data = TennisMatchAnalyzer._get_odds_table_tokens(odds_spread)
        if not odds_data:
            return None
        odds_index = 2 if is_favorite else 0
        if len(odds_data) > odds_index:
            val = float(odds_data[odds_index])
            return -val if is_favorite else val
        return None

    async def _update_player_odds(self, match_vs, player_id, match_id, last_flag, favorite):
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

    async def analyze_match(self, *args, **kwargs):
        today = get_arg(args, 0, kwargs.get("today"))
        match_vs = get_arg(args, 1, kwargs.get("match_vs"))
        player_id = get_arg(args, 2, kwargs.get("player_id"))
        match_id = get_arg(args, 3, kwargs.get("match_id"))
        last_flag = get_arg(args, 4, kwargs.get("last_flag", 0))
        favorite = get_arg(args, 5, kwargs.get("favorite", False))
        default_tour = match_vs[0] if len(match_vs) > 0 and match_vs[0] else ""
        gathered = await asyncio.gather(
            self.fetch_tournament_data(match_id, default_tour=default_tour),
            self.data_fetcher.fetch_player_activities(player_id, match_id)
        )
        tour_now = gathered[0]
        data_act1, data_surf = gathered[1]
        win_percentages = self.extract_win_percentages(data_act1, data_surf)
        match_stats = await self.match_statistics_processor.process_match_statistics(
            player_id, match_id, tour_now, activity_data=data_act1
        )
        nb_match_last_month = self.calculate_matches_last_month(today, data_act1)

        self.update_match_vs(
            match_vs, win_percentages, match_stats, nb_match_last_month, last_flag
        )
        await self._update_player_odds(match_vs, player_id, match_id, last_flag, favorite)

        return match_vs

    async def fetch_tournament_data(self, match_id, default_tour=""):
        return await self.data_fetcher.fetch_tournament_data(match_id, default_tour=default_tour)

    def extract_win_percentages(self, data_act1, data_surf):
        raw_all = self.stats_processor.calculate_win_percentages(data_act1)
        all_percentages = (list(raw_all) + [0.0] * 4)[:4]

        raw_surf = self.stats_processor.calculate_win_percentages(data_surf)
        surf_part = raw_surf[2:] if len(raw_surf) >= 3 else raw_surf
        surface_percentages = (list(surf_part) + [0.0] * 2)[:2]

        return all_percentages + surface_percentages

    async def calculate_win_percentages(self, player_id, match_id):
        data_act1, data_surf = await self.data_fetcher.fetch_player_activities(player_id, match_id)
        return self.extract_win_percentages(data_act1, data_surf)

    @staticmethod
    def calculate_matches_last_month(today, data):
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
        match_vs, win_percentages, match_stats, nb_match_last_month, last_flag
    ):
        offset = 14 + 11 * last_flag
        wp = (list(win_percentages) + [0.0] * 6)[:6]
        ms = (list(match_stats) + [0.0] * 4)[:4]
        match_vs[offset:offset+11] = wp + [nb_match_last_month] + ms

async def last_matchs(*args, **kwargs):
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
