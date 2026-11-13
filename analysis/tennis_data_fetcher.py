"""Client asynchrone TennisInsight avec cache LRU et retries."""

import asyncio
from collections import OrderedDict
from typing import Any, Optional, Tuple
import aiohttp
from bs4 import BeautifulSoup


class TennisDataFetcher:
    """Récupère les panneaux AJAX TennisInsight de manière asynchrone."""

    _activity_pane_cache: OrderedDict[str, str] = OrderedDict()
    _MAX_CACHE_SIZE = 256

    def __init__(self, session: aiohttp.ClientSession, admin_url: Optional[str] = None) -> None:
        self.session = session
        self.admin_url = admin_url

    async def fetch_data(self, url: str, data: Any = None, method: str = "POST") -> str:
        """Exécute une requête HTTP avec backoff linéaire sur 3 tentatives."""
        for attempt in range(3):
            try:
                req = (
                    self.session.get(url)
                    if method.upper() == "GET"
                    else self.session.post(url, data=data)
                )
                async with req as response:
                    if response.status == 200:
                        text = await response.text()
                        if text:
                            return text
            except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError):
                pass
            if attempt < 2:
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
        """Récupère le nom officiel du tournoi depuis le panneau activity."""
        try:
            if match_id not in self._activity_pane_cache:
                pane_req = {"action": "lazyLoadPanes", "pane": "activity", "matchID": match_id}
                html = await self.fetch_data(self.admin_url, pane_req)
                if html:
                    self._activity_pane_cache[match_id] = html
                    if len(self._activity_pane_cache) > self._MAX_CACHE_SIZE:
                        self._activity_pane_cache.popitem(last=False)
            else:
                self._activity_pane_cache.move_to_end(match_id)

            soup = BeautifulSoup(self._activity_pane_cache.get(match_id, ""), "lxml")
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
        odds_option: str = "0",
    ) -> BeautifulSoup:
        """Télécharge un onglet d'activité joueur."""
        player_param = {
            "action": "playerActivity",
            "activityOffset": "0",
            "basic-activity-option": str(activity_option),
            "odds": str(odds_option),
            "filterType": "basic",
            "playerID": player_id,
            "matchID": match_id,
        }
        data_html = await self.fetch_data(self.admin_url, player_param)
        return BeautifulSoup(data_html, "lxml")

    async def fetch_player_activities(
        self, player_id: str, match_id: str
    ) -> Tuple[BeautifulSoup, BeautifulSoup]:
        """Télécharge simultanément l'activité globale et par surface."""
        res1, res2 = await asyncio.gather(
            self.fetch_player_activity(player_id, match_id, 1),
            self.fetch_player_activity(player_id, match_id, 2),
        )
        return res1, res2

    async def fetch_player_activity_with_odds(
        self, player_id: str, match_id: str, activity_option: int, flag: int, favorite: Any
    ) -> BeautifulSoup:
        """Télécharge les performances du joueur selon son statut favori/outsider."""
        odds_option = "5" if favorite[flag] == 1 else "6"
        return await self.fetch_player_activity(
            player_id, match_id, activity_option, odds_option
        )

    async def fetch_match_statistics(self, match_element) -> Optional[BeautifulSoup]:
        """Télécharge les statistiques détaillées d'un match passé."""
        try:
            a_tags = match_element.find_all("a") if match_element else []
            valid_link = len(a_tags) >= 2 and a_tags[1].has_attr("data-action")
            if valid_link and a_tags[1].has_attr("data-matchid"):
                action_data = {
                    "action": a_tags[1]["data-action"],
                    "matchID": a_tags[1]["data-matchid"],
                }
                stats_match_html = await self.fetch_data(self.admin_url, action_data)
                return BeautifulSoup(stats_match_html, "lxml")
        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, AttributeError, IndexError):
            pass
        return None