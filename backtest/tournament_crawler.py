"""
Tournament crawler for discovering and retrieving historical tennis matches.

Fetches historical tournaments and their matches from TennisInsight via AJAX endpoints.
"""

from typing import List, Dict, Any, Tuple
from bs4 import BeautifulSoup
import aiohttp

class TournamentCrawler:
    """Discovers historical ATP/WTA tournaments and match URLs."""

    ADMIN_URL = "https://tennisinsight.com/wp-admin/admin-ajax.php"
    VALID_CATEGORIES = ("250", "500", "1000", "masters", "grand slam", "open", "championships")
    EXCLUDED_CATEGORIES = (" ch ", " itf ", "challenger", "future", "exhibition")

    def __init__(self, admin_url: str = ADMIN_URL):
        self.admin_url = admin_url

    @classmethod
    def is_major_tournament(cls, tour_name: str) -> bool:
        t_low = f" {tour_name.lower()} "
        if any(exc in t_low for exc in cls.EXCLUDED_CATEGORIES):
            return False
        return any(cat in t_low for cat in cls.VALID_CATEGORIES)

    async def fetch_tournaments(
        self,
        session: aiohttp.ClientSession,
        year: int
    ) -> List[Dict[str, str]]:
        payload = {
            "action": "searchTournaments",
            "tournament_search_name": "",
            "tournament_search_year": str(year)
        }
        async with session.post(self.admin_url, data=payload) as resp:
            html = await resp.text()

        soup = BeautifulSoup(html, "lxml")
        results = []
        for a in soup.find_all("a", href=True):
            if "/tournament/" in a["href"]:
                name = a.text.strip()
                if self.is_major_tournament(name):
                    tid = a["href"].split("/tournament/")[1].split("/")[0]
                    results.append({"id": tid, "name": name, "url": a["href"]})
        return results

    async def fetch_tournament_matches(
        self,
        session: aiohttp.ClientSession,
        tournament_id: str
    ) -> List[str]:
        payload = {
            "action": "lazyLoadPanes",
            "pane": "results",
            "tournamentID": str(tournament_id)
        }
        async with session.post(self.admin_url, data=payload) as resp:
            html = await resp.text()

        soup = BeautifulSoup(html, "lxml")
        seen = set()
        matches = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/match/" in href and href not in seen:
                seen.add(href)
                matches.append(href)
        return matches
