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
        """Checks if tournament category matches primary circuit criteria."""
        t_low = f" {tour_name.lower()} "
        if any(exc in t_low for exc in cls.EXCLUDED_CATEGORIES):
            return False
        return any(cat in t_low for cat in cls.VALID_CATEGORIES)

    async def fetch_tournaments(
            self,
            session: aiohttp.ClientSession,
            year: int
    ) -> List[Dict[str, str]]:
        """Fetches tournament directory and lists tournament URLs."""
        payload = {
            "action": "searchTournaments",
            "tournament_search_name": "",
            "tournament_search_year": str(year)
        }
        async with session.post(self.admin_url, data=payload) as resp:
            html = await resp.text()

        soup = BeautifulSoup(html, "lxml")
        results = []
        for link_elem in soup.find_all("a"):
            href = link_elem.get("href", "")
            if "/tournament/" in href:
                name = link_elem.text.strip()
                if self.is_major_tournament(name):
                    tid = href.split("/tournament/")[1].split("/")[0]
                    results.append({"id": tid, "name": name, "url": href})
        return results

    async def fetch_tournament_matches(
            self,
            session: aiohttp.ClientSession,
            tournament_id: str
    ) -> List[str]:
        """Fetches all match preview URLs for a tournament ID."""
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
        for link_elem in soup.find_all("a"):
            href = link_elem.get("href", "")
            if "/match/" in href and href not in seen:
                seen.add(href)
                matches.append(href)
        return matches
