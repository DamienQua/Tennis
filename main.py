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
from data_providers.ELO_table import ELO_table
from core.analyze_match import analyze_match
from aiolimiter import AsyncLimiter
from collections import namedtuple
from core.match_filter import MatchFilter
from core.match_repository import MatchRepository

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

    async def process(self, match_url: str, tournaments: Any, elo_data: str, max_retries: int = 2) -> Optional[str]:
        if not self.should_process(match_url):
            return None

        for attempt in range(max_retries):
            start = time.perf_counter()
            try:
                match_info = await self.fetch_and_analyze(match_url, tournaments, elo_data)
                if not match_info:
                    return None
                return self.finalize_result(match_info, match_url, start)
            except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError) as e:
                if attempt < max_retries - 1:
                    print(f"⚠️ Erreur temporaire ({type(e).__name__}) sur {match_url}, nouvelle tentative...")
                    await asyncio.sleep(2.0)
                else:
                    return await self.handle_connection_error(match_url, e)
            except Exception as e:
                print(f"Erreur lors de l'analyse du match {match_url}: {type(e).__name__} {e}")
                return None
        return None

    async def handle_connection_error(self, match_url: str = "", error: Optional[Exception] = None) -> None:
        err_msg = f": {type(error).__name__} {error}" if error else ""
        print(f"Erreur lors de l'analyse du match {match_url}{err_msg}")
        return None

    def finalize_result(self, match_info: str, match_url: str, start: float) -> str:
        result = self.format_result(match_info, match_url)
        raw_elapsed = round(time.perf_counter() - start, 2)
        print(f"Match : {result}")
        print(f"Time elapsed : {raw_elapsed} sec\n")
        return result

async def fetch_data(session: aiohttp.ClientSession, url: str, method: str = 'get', data: Optional[dict] = None) -> str:
    methods = {
        'get': session.get,
        'post': session.post
    }
    async with methods[method](url, data=data) as response:
        return await response.text()

def create_session_config(max_concurrent: int = 15, timeout_seconds: float = 30.0) -> SessionConfig:
    header = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    conn = aiohttp.TCPConnector(limit=max_concurrent)
    rate_limit = AsyncLimiter(10, 1)  # 10 requests per second
    timeout = aiohttp.ClientTimeout(total=timeout_seconds, connect=10.0)
    return SessionConfig(header, conn, rate_limit, timeout)

def _clean_val(val: str, prefix: str) -> str:
    clean = val.strip().strip('"').strip("'")
    if clean.startswith(f"{prefix}="):
        return clean.split("=", 1)[1].strip().strip('"').strip("'")
    return clean

def _get_credential(config: dict, key: str) -> str:
    val = os.environ.get(key)
    if not val:
        val = config.get(key, "")
    return _clean_val(val, key)

async def login(session: aiohttp.ClientSession) -> None:
    config = dotenv_values(".env") if os.path.exists(".env") else {}
    username = _get_credential(config, "TENNISINSIGHT_LOGIN")
    password = _get_credential(config, "TENNISINSIGHT_PASSWORD")
    if not username or not password:
        has_env_login = bool(os.environ.get("TENNISINSIGHT_LOGIN"))
        has_env_pass = bool(os.environ.get("TENNISINSIGHT_PASSWORD"))
        print(f"DEBUG: env TENNISINSIGHT_LOGIN={has_env_login}, env TENNISINSIGHT_PASSWORD={has_env_pass}")
        raise ValueError("Erreur: Les identifiants TENNISINSIGHT_LOGIN et TENNISINSIGHT_PASSWORD doivent être définis (dans les variables d'environnement ou le fichier .env)")
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
    _notify_daily_results(matchs)

def _notify_daily_results(matchs_str: str) -> None:
    from strategy.alpha_tracker import get_session_bets
    from strategy.email_notifier import send_daily_email

    total_matches = len([line for line in (matchs_str or "").split("\n") if line.strip()])
    bets = get_session_bets()
    send_daily_email(bets, total_matches=total_matches)

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
        await asyncio.sleep(0.5)
        return m_i

async def process_matches(
    session: aiohttp.ClientSession,
    session_config: SessionConfig,
    tournaments: Any,
    mtch: List[str],
    atp_elo: str,
    wta_elo: str,
    repository: MatchRepository,
    max_parallel_matches: int = 1
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