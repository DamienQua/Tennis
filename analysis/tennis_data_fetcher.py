"""Client asynchrone TennisInsight avec cache LRU, déduplication in-flight et retries."""

import asyncio
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple
import weakref
import aiohttp
from bs4 import BeautifulSoup
from utils.helpers import fetch_with_retry


class TennisDataFetcher:
    """Récupère les panneaux AJAX TennisInsight de manière asynchrone."""

    _activity_pane_cache: OrderedDict[str, str] = OrderedDict()
    _MAX_CACHE_SIZE = 256
    _locks_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Dict[str, asyncio.Lock]]" = (
        weakref.WeakKeyDictionary()
    )

    def __init__(self, session: aiohttp.ClientSession, admin_url: Optional[str] = None) -> None:
        self.session = session
        self.admin_url = admin_url

    @classmethod
    def _get_inflight_lock(cls, key: str) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        loop_locks = cls._locks_by_loop.setdefault(loop, {})
        if len(loop_locks) > cls._MAX_CACHE_SIZE * 2:
            idle_keys = [
                k for k, lk in loop_locks.items()
                if not lk.locked() and not getattr(lk, "_waiters", None)
            ]
            for k in idle_keys[:cls._MAX_CACHE_SIZE]:
                loop_locks.pop(k, None)
        lock = loop_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            loop_locks[key] = lock
        return lock

    async def fetch_data(self, url: str, data: Any = None, method: str = "POST") -> str:
        """Exécute une requête HTTP avec backoff linéaire sur 3 tentatives."""
        return await fetch_with_retry(
            self.session, url, method=method, data=data, attempts=3, backoff_step=1.5
        )

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

    async def _fetch_activity_pane_html(self, match_id: str) -> str:
        if match_id in self._activity_pane_cache:
            self._activity_pane_cache.move_to_end(match_id)
            return self._activity_pane_cache[match_id]

        async with self._get_inflight_lock(match_id):
            if match_id in self._activity_pane_cache:
                self._activity_pane_cache.move_to_end(match_id)
                return self._activity_pane_cache[match_id]

            pane_req = {"action": "lazyLoadPanes", "pane": "activity", "matchID": match_id}
            html = await self.fetch_data(self.admin_url, pane_req)
            if html:
                self._activity_pane_cache[match_id] = html
                if len(self._activity_pane_cache) > self._MAX_CACHE_SIZE:
                    self._activity_pane_cache.popitem(last=False)
            return html

    async def fetch_tournament_data(self, match_id: str, default_tour: str = "") -> str:
        """Récupère le nom officiel du tournoi depuis le panneau activity (dédupliqué)."""
        try:
            html = await self._fetch_activity_pane_html(match_id)
            soup = BeautifulSoup(html, "lxml")
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
