"""Récupération asynchrone des classements ELO avec cache disque TTL."""

import os
import time
from typing import Dict, Optional
import aiohttp
from bs4 import BeautifulSoup

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
ELO_CACHE_TTL_SECONDS = 12 * 3600  # 12 heures


class EloFetcher:
    """Télécharge et met en cache les pages HTML des classements ELO."""

    cache: Dict[str, str] = {}

    @classmethod
    async def fetch_data(
        cls,
        url: str,
        user_agent: str = DEFAULT_USER_AGENT,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> str:
        if url in cls.cache:
            return cls.cache[url]

        headers = {"User-Agent": user_agent}
        if session is not None:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                content = await response.text()
        else:
            timeout = aiohttp.ClientTimeout(total=15.0)
            async with aiohttp.ClientSession(timeout=timeout) as temp_session:
                async with temp_session.get(url, headers=headers) as response:
                    response.raise_for_status()
                    content = await response.text()

        cls.cache[url] = content
        return content


def _read_fresh_cache(filepath: str, max_age_seconds: int) -> Optional[str]:
    """Retourne le contenu du fichier local s'il existe et n'a pas expiré."""
    if not os.path.exists(filepath):
        return None
    age = time.time() - os.path.getmtime(filepath)
    if age <= max_age_seconds:
        with open(filepath, "r", encoding="utf-8") as file_handle:
            content = file_handle.read()
            if content.strip():
                return content
    return None


async def elo_table(
    circuit: str,
    session: Optional[aiohttp.ClientSession] = None,
    ttl_seconds: int = ELO_CACHE_TTL_SECONDS,
) -> str:
    """Récupère la table ELO ATP/WTA depuis le cache disque ou Tennis Abstract."""
    cache_file = f"{circuit}_ELO.txt"
    cached = _read_fresh_cache(cache_file, ttl_seconds)
    if cached is not None:
        return cached

    url = f"https://tennisabstract.com/reports/{circuit.lower()}_elo_ratings.html"
    content = await EloFetcher.fetch_data(url, session=session)
    soup = BeautifulSoup(content, "lxml")
    tr_elements = soup.find_all("tr")[3:]

    lines = []
    for row in tr_elements:
        cells = row.find_all("td")
        if len(cells) < 11:
            continue
        name = cells[1].text.replace("\xa0", " ").strip()
        lines.append(f"{name} {cells[6].text} {cells[8].text} {cells[10].text}\n")

    elo_str = "".join(lines)
    with open(cache_file, "w", encoding="utf-8") as file_handle:
        file_handle.write(elo_str)
    return elo_str