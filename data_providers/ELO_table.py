"""
Asynchronously fetch and parse ELO ratings from Tennis Abstract for a given gender.

This function retrieves ELO ratings for male or female tennis players from the
Tennis Abstract website, and writes them to a text file while returning them.

Args:
    m_w (str): Gender specification, either 'men' or 'women'

Returns:
    str: A string containing ELO ratings for tennis players

Notes:
    - Creates a text file named '{m_w}_ELO.txt' with the parsed ratings
    - Uses a cached HTTP request to improve performance
    - Requires an internet connection to fetch the latest ratings
"""

import aiohttp
from bs4 import BeautifulSoup
from typing import Dict

class EloFetcher:
    """Fetches and caches ELO ratings HTML content."""
    cache: Dict[str, str] = {}

    @classmethod
    async def fetch_data(cls, url: str, user_agent: str) -> str:
        """Fetches Elo table web page asynchronously."""
        if url in cls.cache:
            return cls.cache[url]
        headers = {'User-Agent': user_agent}
        timeout = aiohttp.ClientTimeout(total=15.0)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                content = await response.text()
                cls.cache[url] = content
                return content

_FETCH_CACHE = EloFetcher.cache
fetch_data = EloFetcher.fetch_data

async def elo_table(m_w: str) -> str:
    """Retrieves and formats live Elo table for ATP or WTA circuit."""
    table = ""
    elo = ""
    user_agent = (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
    )
    url = "https://tennisabstract.com/reports/" + m_w.lower() + "_elo_ratings.html"

    content = await fetch_data(url, user_agent)
    soup = BeautifulSoup(content, 'lxml')
    tr_elements = soup.find_all("tr")[3:]

    with open(f"{m_w}_ELO.txt", "w", encoding="utf-8") as file_handle:
        for table_row in tr_elements:
            table_cells = table_row.find_all("td")
            name = table_cells[1].text.replace("\xa0", " ")
            table = f"{name} {table_cells[6].text} {table_cells[8].text} {table_cells[10].text}\n"
            file_handle.write(table)
            elo += table

    return elo
