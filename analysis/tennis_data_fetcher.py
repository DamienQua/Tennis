"""
Module for fetching tennis match and player activity data asynchronously from TennisInsight.
"""

import asyncio
from typing import Any, Dict, Optional

import aiohttp
from bs4 import BeautifulSoup


class TennisDataFetcher:
    """Retrieves HTML and statistical data asynchronously with retry logic."""

    _activity_pane_cache: Dict[str, str] = {}

    def __init__(self, session: aiohttp.ClientSession, admin_url: Optional[str] = None):
        self.session = session
        self.admin_url = admin_url

    async def fetch_data(self, url: str, data: Any = None, method: str = 'POST') -> str:
        """Fetches HTML data asynchronously with retry logic."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                req = (
                    self.session.get(url)
                    if method.upper() == 'GET'
                    else self.session.post(url, data=data)
                )
                async with req as response:
                    if response.status == 200:
                        text = await response.text()
                        if text:
                            return text
            except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError):
                pass
            if attempt < max_retries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
        return ""

    @staticmethod
    def _extract_tournament_name(soup: BeautifulSoup) -> str:
        for elem_id in ("basic-this-tournament-A", "basic-this-tournament-B"):
            elem = soup.find(id=elem_id)
            val = elem.get("value") if elem else ""
            if "At " in val:
                parts = val.split("At ")
                if len(parts) > 1 and parts[1].strip():
                    return parts[1].strip()
        return ""

    async def fetch_tournament_data(self, match_id: str, default_tour: str = "") -> str:
        """Fetches tournament metadata and parses tournament name."""
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

    async def fetch_player_activity(
            self,
            player_id: str,
            match_id: str,
            activity_option: int,
            odds_option: str = "0"
    ) -> BeautifulSoup:
        """Fetches player activity pane HTML for a given page index."""
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

    async def fetch_player_activities(self, player_id: str, match_id: str):
        """Fetches activity and surface statistics panes concurrently."""
        return await asyncio.gather(
            self.fetch_player_activity(player_id, match_id, 1),
            self.fetch_player_activity(player_id, match_id, 2)
        )

    async def fetch_player_activity_with_odds(
            self, player_id: str, match_id: str, activity_option: int, flag: int, favorite: Any
    ) -> BeautifulSoup:
        """Fetches activity pane and odds spread concurrently."""
        odds_option = "5" if favorite[flag] == 1 else "6"
        return await self.fetch_player_activity(
            player_id, match_id, activity_option, odds_option
        )

    async def fetch_match_statistics(self, match_element) -> Optional[BeautifulSoup]:
        """Fetches detailed statistics for a specific match element."""
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
