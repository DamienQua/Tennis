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

import os
os.environ.pop('SSLKEYLOGFILE', None)
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import time
from datetime import datetime
from dotenv import dotenv_values
import numpy as np
from typing import List, Tuple, Optional, Any
from ELO_table import ELO_table
from analyze_match import analyze_match
from aiolimiter import AsyncLimiter
from collections import namedtuple
from match_filter import MatchFilter
from match_repository import MatchRepository

SessionConfig = namedtuple('SessionConfig', ['header', 'connector', 'rate_limit', 'timeout'])

class MatchProcessor:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        header: dict,
        rate_limit: AsyncLimiter,
        already_processed: str,
        match_filter: Optional[MatchFilter] = None
    ) -> None:
        self.session = session
        self.header = header
        self.rate_limit = rate_limit
        self.already_processed = already_processed
        self.filter = match_filter or MatchFilter()

    def should_process(self, match_url: str) -> bool:
        return self.filter.should_process(match_url, self.already_processed)

    async def fetch_and_analyze(self, match_url: str, tournaments: Any, elo_data: str) -> str:
        async with self.rate_limit:
            return await analyze_match(self.session, self.header, match_url, tournaments, elo_data)

    def format_result(self, match_info: str, match_url: str) -> str:
        return f"{match_info}, {match_url}"

    async def process(self, match_url: str, tournaments: Any, elo_data: str) -> Optional[str]:
        if not self.should_process(match_url):
            return None

        start = time.perf_counter()

        try:
            match_info = await self.fetch_and_analyze(match_url, tournaments, elo_data)
        except aiohttp.ClientError:
            return await self.handle_connection_error()
        except Exception as e:
            print(f"Erreur lors de l'analyse du match {match_url}: {e}")
            return None

        if not match_info:
            return None

        return self.finalize_result(match_info, match_url, start)

    async def handle_connection_error(self) -> None:
        print("Connection error, retrying...")
        await asyncio.sleep(1)
        return None

    def finalize_result(self, match_info: str, match_url: str, start: float, parallel_count: int = 3) -> str:
        result = self.format_result(match_info, match_url)
        raw_elapsed = round(time.perf_counter() - start, 2)
        effective_time = round(raw_elapsed / parallel_count, 2)
        print(f"Match : {result}")
        print(f"Time elapsed : {raw_elapsed} sec (temps effectif amorti: ~{effective_time} sec/match)\n")
        return result

async def fetch_data(session: aiohttp.ClientSession, url: str, method: str = 'get', data: Optional[dict] = None) -> str:
    methods = {
        'get': session.get,
        'post': session.post
    }
    async with methods[method](url, data=data) as response:
        return await response.text()

def create_session_config(max_concurrent: int = 10, timeout_seconds: float = 20.0) -> SessionConfig:
    header = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
    conn = aiohttp.TCPConnector(limit=max_concurrent)
    rate_limit = AsyncLimiter(10, 1)  # 10 requests per second
    timeout = aiohttp.ClientTimeout(total=timeout_seconds, connect=10.0)
    return SessionConfig(header, conn, rate_limit, timeout)

async def login(session: aiohttp.ClientSession) -> None:
    config = dotenv_values(".env")
    username = config.get("TENNISINSIGHT_LOGIN")
    password = config.get("TENNISINSIGHT_PASSWORD")
    if not username or not password:
        raise ValueError("Erreur: Les identifiants TENNISINSIGHT_LOGIN et TENNISINSIGHT_PASSWORD doivent être définis dans le fichier .env")
    login_data = {"log": username, "pwd": password}
    await fetch_data(session, "https://tennisinsight.com/wp-login.php", method='post', data=login_data)

async def fetch_match_previews(session: aiohttp.ClientSession) -> Tuple[np.ndarray, List[str]]:
    mtch_previews_html = await fetch_data(session, "https://tennisinsight.com/match-previews/")
    mtch_previews = BeautifulSoup(mtch_previews_html, "lxml")
    tournaments = np.array([tour.text for tour in mtch_previews.find_all(class_="heading-link") if any(x in tour.text for x in ["ATP", "WTA", "Masters"])])
    mtch = [m.a["href"] for m in mtch_previews.find_all(class_="match-row-link")]
    return tournaments, mtch

async def main() -> None:
    session_config = create_session_config()
    repository = MatchRepository()
    atp_elo, wta_elo = await load_elo_tables()

    async with aiohttp.ClientSession(
        connector=session_config.connector,
        headers=session_config.header,
        timeout=session_config.timeout
    ) as session:
        await login(session)
        tournaments, mtch = await fetch_match_previews(session)
        matchs = await process_matches(session, session_config, tournaments, mtch, atp_elo, wta_elo, repository)

    print(matchs)

async def load_elo_tables() -> Tuple[str, str]:
    atp_elo = await ELO_table("ATP")
    wta_elo = await ELO_table("WTA")
    return atp_elo, wta_elo

async def _process_single_match(
    m: str,
    tournaments: Any,
    elo_data: str,
    processor: MatchProcessor,
    semaphore: asyncio.Semaphore,
    repository: MatchRepository,
    lock: asyncio.Lock,
    results: List[str]
) -> Optional[str]:
    async with semaphore:
        m_i = await processor.process(m, tournaments, elo_data)
        if m_i:
            async with lock:
                results.append(m_i)
                all_matchs = "\n".join(results) + "\n"
                repository.save_processed_match(m_i, all_matchs)
        return m_i

async def process_matches(
    session: aiohttp.ClientSession,
    session_config: SessionConfig,
    tournaments: Any,
    mtch: List[str],
    atp_elo: str,
    wta_elo: str,
    repository: MatchRepository,
    max_parallel_matches: int = 3
) -> str:
    already = repository.load_reviewed_matches()
    processor = MatchProcessor(session, session_config.header, session_config.rate_limit, already)
    semaphore = asyncio.Semaphore(max_parallel_matches)
    lock = asyncio.Lock()
    results: List[str] = []

    batch_start = time.perf_counter()
    tasks = [
        _process_single_match(
            m,
            tournaments,
            determine_elo_data(m, atp_elo, wta_elo),
            processor,
            semaphore,
            repository,
            lock,
            results
        )
        for m in mtch
    ]
    await asyncio.gather(*tasks)
    total_elapsed = round(time.perf_counter() - batch_start, 2)
    count = len(results)
    avg_per_match = round(total_elapsed / count, 2) if count > 0 else 0.0
    print(f"\n{'='*55}")
    print(f"Total processing time : {total_elapsed} sec ({count} match(s) processed)")
    print(f"Average time per match: {avg_per_match} sec/match")
    print(f"{'='*55}\n")
    return "\n".join(results) + "\n" if results else ""

def determine_elo_data(match_url: str, atp_elo: str, wta_elo: str) -> str:
    if "atp" in match_url or ("wta" not in match_url and "masters" in match_url):
        return atp_elo + '\n' + wta_elo
    return wta_elo + '\n' + atp_elo

if __name__ == "__main__":
    asyncio.run(main())