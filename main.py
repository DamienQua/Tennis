"""
A class for processing tennis match data asynchronously with configurable filtering and analysis.

Handles fetching, analyzing, and processing match previews from a tennis website, with support for:
- Rate-limited web requests
- Match URL filtering based on year and tournament type
- Special case handling for specific player names
- Performance tracking and error handling

Attributes:
    session (aiohttp.ClientSession): HTTP session for web requests
    header (dict): HTTP request headers
    rate_limit (AsyncLimiter): Request rate limiting configuration
    already_processed (str): Tracking of previously processed matches
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import time
import numpy as np
from ELO_table import ELO_table
from analyze_match import analyze_match
from aiolimiter import AsyncLimiter
from collections import namedtuple

SessionConfig = namedtuple('SessionConfig', ['header', 'connector', 'rate_limit'])

class MatchProcessor:
    def __init__(self, session, header, rate_limit, already_processed):
        self.session = session
        self.header = header
        self.rate_limit = rate_limit
        self.already_processed = already_processed

    def should_process_match(self, match_url):
        return (("2025" in match_url) and 
                (any(subword in match_url for subword in ("atp", "wta", "masters"))) and 
                not ("/q/" in match_url or "tba-tba" in match_url) and 
                match_url not in self.already_processed)

    async def fetch_and_analyze(self, match_url, tournaments, elo_data):
        async with self.rate_limit:
            return await analyze_match(self.session, self.header, match_url, tournaments, elo_data)

    def format_result(self, match_info, match_url):
        return f"{match_info}, {match_url}"

    async def process(self, match_url, tournaments, elo_data):
        if not self.should_process_match(match_url):
            if not self.is_special_case(match_url):
                return None

        start = time.perf_counter()

        try:
            match_info = await self.fetch_and_analyze(match_url, tournaments, elo_data)
        except aiohttp.ClientError:
            return await self.handle_connection_error()

        return self.finalize_result(match_info, match_url, start)

    def is_special_case(self, match_url):
        return any(name in match_url for name in ["fruhvirtova", "noskova", "efremova", "andreeva", "krueger"])

    async def handle_connection_error(self):
        print("Connection error, retrying...")
        await asyncio.sleep(1)
        return None

    def finalize_result(self, match_info, match_url, start):
        result = self.format_result(match_info, match_url)
        print("Match : ", result)
        print("Time elapsed : ", round(time.perf_counter() - start, 2), " sec")
        return result

async def fetch_data(session, url, method='get', data=None):
    methods = {
        'get': session.get,
        'post': session.post
    }
    async with methods[method](url, data=data) as response:
        return await response.text()

def create_session_config():
    header = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
    conn = aiohttp.TCPConnector(limit=10)  # 10 simultaneous connections
    rate_limit = AsyncLimiter(10, 1)  # 10 requests per second
    return SessionConfig(header, conn, rate_limit)

def load_reviewed_matches():
    try:
        with open("Reviewed_Matchs.txt", "r") as f:
            return f.read()
    except:
        return ""

async def login(session):
    login_data = {"log": "", "pwd": ""}
    await fetch_data(session, "https://tennisinsight.com/wp-login.php", method='post', data=login_data)

async def fetch_match_previews(session):
    mtch_previews_html = await fetch_data(session, "https://tennisinsight.com/match-previews/")
    mtch_previews = BeautifulSoup(mtch_previews_html, "lxml")
    tournaments = np.array([tour.text for tour in mtch_previews.find_all(class_="heading-link") if any(x in tour.text for x in ["ATP", "WTA", "Masters"])])
    mtch = [m.a["href"] for m in mtch_previews.find_all(class_="match-row-link")]
    return tournaments, mtch

def update_match_files(m_i, matchs):
    with open("Reviewed_Matchs.txt", "a") as old:
        old.write(m_i + "\n")
    with open("Matchs.txt", "w") as new:
        new.write(matchs)

async def main():
    session_config = create_session_config()
    atp_elo, wta_elo = await load_elo_tables()
    already = load_reviewed_matches()

    async with aiohttp.ClientSession(connector=session_config.connector, headers=session_config.header) as session:
        await login(session)
        tournaments, mtch = await fetch_match_previews(session)
        matchs = await process_matches(session, session_config, tournaments, mtch, atp_elo, wta_elo, already)

    print(matchs)

async def load_elo_tables():
    atp_elo = await ELO_table("ATP")
    wta_elo = await ELO_table("WTA")
    return atp_elo, wta_elo

async def process_matches(session, session_config, tournaments, mtch, atp_elo, wta_elo, already):
    processor = MatchProcessor(session, session_config.header, session_config.rate_limit, already)
    matchs = ""
    matchs_tab = np.chararray(256, itemsize=100, unicode=True)
    i = 0

    for m in mtch:
        elo_data = determine_elo_data(m, atp_elo, wta_elo)
        m_i = await processor.process(m, tournaments, elo_data)
        if m_i:
            matchs += m_i + "\n"
            matchs_tab[i] = m_i
            i += 1
            update_match_files(m_i, matchs)
    return matchs

def determine_elo_data(match_url, atp_elo, wta_elo):
    if "atp" in match_url or ("wta" not in match_url and "masters" in match_url):
        return atp_elo + '\n' + wta_elo
    return wta_elo + '\n' + atp_elo

if __name__ == "__main__":
    asyncio.run(main())