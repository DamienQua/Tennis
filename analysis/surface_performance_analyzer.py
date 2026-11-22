"""Évaluation de la performance relative sur la surface du match."""

import asyncio
from collections import OrderedDict
from typing import Dict
import weakref
import aiohttp
from bs4 import BeautifulSoup


class SurfacePerformanceAnalyzer:
    """Calcule le rang de performance surface avec cache LRU borné et verrou in-flight."""

    SURFACE_INDICES = {"Hard": 12, "Indoor Hard": 19, "Carpet": 26, "Clay": 33, "Grass": 40}
    _stats_cache: OrderedDict[str, str] = OrderedDict()
    _MAX_CACHE_SIZE = 256
    _locks_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Dict[str, asyncio.Lock]]" = (
        weakref.WeakKeyDictionary()
    )

    def __init__(self, data_fetcher, admin_url: str) -> None:
        self.data_fetcher = data_fetcher
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

    async def fetch_statistics_html(self, match_id: str) -> str:
        """Récupère et met en cache le panneau statistiques du match sans doublon in-flight."""
        if match_id in self._stats_cache:
            self._stats_cache.move_to_end(match_id)
            return self._stats_cache[match_id]

        async with self._get_inflight_lock(match_id):
            if match_id in self._stats_cache:
                self._stats_cache.move_to_end(match_id)
                return self._stats_cache[match_id]

            pane_req = {"action": "lazyLoadPanes", "pane": "statistics", "matchID": match_id}
            html = await self.data_fetcher.fetch_data(self.admin_url, pane_req)
            if html:
                self._stats_cache[match_id] = html
                if len(self._stats_cache) > self._MAX_CACHE_SIZE:
                    self._stats_cache.popitem(last=False)
            return html

    @classmethod
    def _find_surface_index(cls, surface: str):
        idx = cls.SURFACE_INDICES.get(surface)
        if idx is not None:
            return idx
        for name, index in cls.SURFACE_INDICES.items():
            if name.lower() in surface.lower():
                return index
        return None

    @staticmethod
    def _extract_tds(data: BeautifulSoup, flag: int):
        table_idx = 1 if flag == 0 else 4
        tables = data.find_all(class_="table match-preview-statistics-table")
        if len(tables) > table_idx:
            return tables[table_idx].find_all("td")
        return []

    @staticmethod
    def _calculate_surface_rank(tds, target_idx: int) -> int:
        win_sur = float(tds[target_idx].text.replace("%", "").replace("N/A", "0"))
        rank = 10
        for idx in range(12, min(len(tds), 41), 7):
            val = float(tds[idx].text.replace("%", "").replace("N/A", "0"))
            if win_sur > val:
                rank += 10
        return rank

    async def analyze(self, match_id: str, surface: str, flag: int) -> int:
        """Calcule l'indice de rang surface en exploitant le cache."""
        try:
            stats_html = await self.fetch_statistics_html(match_id)
            target_idx = self._find_surface_index(surface)
            if target_idx is None or not stats_html:
                return 10
            tds = self._extract_tds(BeautifulSoup(stats_html, "lxml"), flag)
            if len(tds) <= target_idx:
                return 10
            return self._calculate_surface_rank(tds, target_idx)
        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            IndexError,
            ValueError,
            AttributeError,
            KeyError,
        ):
            return 10
