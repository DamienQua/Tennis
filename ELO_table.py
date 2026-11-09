"""
Asynchronously fetch and parse ELO ratings from Tennis Abstract for a given gender.

This function retrieves ELO ratings for male or female tennis players from the Tennis Abstract website,
and writes the ratings to a text file while also returning them as a string.

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
import functools

class EloFetcher:
    """Fetches and caches ELO ratings HTML content."""
    cache = {}

    @classmethod
    async def fetch_data(cls, url, user_agent):
        if url in cls.cache:
            return cls.cache[url]
        headers = {'User-Agent': user_agent}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                content = await response.text()
                cls.cache[url] = content
                return content

_FETCH_CACHE = EloFetcher.cache
fetch_data = EloFetcher.fetch_data

async def ELO_table(m_w):
    table = ""
    elo = ""
    user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
    url = "https://tennisabstract.com/reports/" + m_w.lower() + "_elo_ratings.html"
    
    content = await fetch_data(url, user_agent)
    soup = BeautifulSoup(content, 'lxml')
    tr_elements = soup.find_all("tr")[3:]

    with open(f"{m_w}_ELO.txt", "w", encoding="utf-8") as f:
        for tr in tr_elements:
            td = tr.find_all("td")
            table = td[1].text.replace("\xa0", " ") + " " + td[6].text + " " + td[8].text + " " + td[10].text + "\n"
            f.write(table)
            elo += table
    
    return elo