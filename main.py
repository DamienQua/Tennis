"""Point d'entrée principal du pipeline asynchrone d'analyse de matchs de tennis."""

import asyncio
import logging
import os
import time
from typing import List, NamedTuple, Optional, Sequence, Set, Tuple
import aiohttp
from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from dotenv import dotenv_values
import numpy as np

from core.analyze_match import analyze_match
from core.match_filter import MatchFilter
from core.match_repository import MatchRepository
from data_providers.elo_table import elo_table
from strategy.alpha_tracker import get_session_bets
from strategy.email_notifier import send_daily_email

os.environ.pop("SSLKEYLOGFILE", None)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class SessionConfig(NamedTuple):
    """Configuration de session HTTP, limiteur de débit et timeouts."""

    header: dict
    connector: aiohttp.TCPConnector
    rate_limit: AsyncLimiter
    timeout: aiohttp.ClientTimeout


class MatchProcessor:
    """Gère le filtrage, les reprises réseau et l'analyse d'un match."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        header: dict,
        rate_limit: AsyncLimiter,
        already_processed: Set[str],
        match_filter: Optional[MatchFilter] = None,
    ) -> None:
        self.session = session
        self.header = header
        self.rate_limit = rate_limit
        self.already_processed = already_processed
        self.filter = match_filter or MatchFilter()

    def should_process(self, match_url: str) -> bool:
        return self.filter.should_process(match_url, self.already_processed)

    async def fetch_and_analyze(
        self, match_url: str, tournaments: Sequence[str], elo_data: str
    ) -> Optional[str]:
        async with self.rate_limit:
            match_data = await analyze_match(
                self.session, self.header, match_url, tournaments, elo_data
            )
            return match_data.to_summary_line() if match_data else None

    @staticmethod
    def format_result(match_info: str, match_url: str) -> str:
        return f"{match_info}, {match_url}"

    async def process(
        self,
        match_url: str,
        tournaments: Sequence[str],
        elo_data: str,
        max_retries: int = 2,
    ) -> Optional[str]:
        """Exécute l'analyse complète d'un match avec gestion des erreurs temporaires."""
        if not self.should_process(match_url):
            return None

        for attempt in range(max_retries):
            start = time.perf_counter()
            try:
                match_info = await self.fetch_and_analyze(match_url, tournaments, elo_data)
                if not match_info:
                    return None
                return self.finalize_result(match_info, match_url, start)
            except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError) as err:
                if attempt < max_retries - 1:
                    logger.warning(
                        "Erreur temporaire (%s) sur %s, nouvelle tentative...",
                        type(err).__name__,
                        match_url,
                    )
                    await asyncio.sleep(2.0)
                else:
                    logger.error("Échec réseau sur %s : %s", match_url, err)
                    return None
            except (
                IndexError,
                KeyError,
                ValueError,
                TypeError,
                AttributeError,
                OSError,
                RuntimeError,
            ) as err:
                logger.error(
                    "Erreur d'analyse sur %s : %s %s", match_url, type(err).__name__, err
                )
                return None
        return None

    def finalize_result(self, match_info: str, match_url: str, start: float) -> str:
        result = self.format_result(match_info, match_url)
        raw_elapsed = round(time.perf_counter() - start, 2)
        print(f"Match : {result}")
        print(f"Time elapsed : {raw_elapsed} sec\n")
        return result


class BatchContext:
    """Contexte partagé d'exécution concurrente."""

    def __init__(
        self,
        processor: MatchProcessor,
        semaphore: asyncio.Semaphore,
        repository: Optional[MatchRepository],
        lock: asyncio.Lock,
        results: List[str],
    ) -> None:
        self.processor = processor
        self.semaphore = semaphore
        self.repository = repository
        self.lock = lock
        self.results = results


def create_session_config(
    max_concurrent: int = 15, timeout_seconds: float = 30.0
) -> SessionConfig:
    """Initialise les paramètres de la session HTTP."""
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    header = {"User-Agent": user_agent}
    conn = aiohttp.TCPConnector(limit=max_concurrent)
    rate_limit = AsyncLimiter(10, 1)
    timeout = aiohttp.ClientTimeout(total=timeout_seconds, connect=10.0)
    return SessionConfig(header, conn, rate_limit, timeout)


def _clean_val(val: str, prefix: str) -> str:
    clean = val.strip().strip('"').strip("'")
    if clean.startswith(f"{prefix}="):
        return clean.split("=", 1)[1].strip().strip('"').strip("'")
    return clean


def _get_credential(config: dict, key: str) -> str:
    val = os.environ.get(key) or config.get(key, "")
    return _clean_val(val, key)


async def login(session: aiohttp.ClientSession) -> None:
    """Authentifie la session HTTP sur TennisInsight."""
    config = dotenv_values(".env") if os.path.exists(".env") else {}
    username = _get_credential(config, "TENNISINSIGHT_LOGIN")
    password = _get_credential(config, "TENNISINSIGHT_PASSWORD")
    if not username or not password:
        raise ValueError(
            "Les identifiants TENNISINSIGHT_LOGIN et TENNISINSIGHT_PASSWORD "
            "doivent être définis dans l'environnement ou le fichier .env."
        )
    async with session.post(
        "https://tennisinsight.com/wp-login.php",
        data={"log": username, "pwd": password},
    ) as resp:
        resp.raise_for_status()


async def fetch_match_previews(session: aiohttp.ClientSession) -> Tuple[np.ndarray, List[str]]:
    """Récupère les tournois actifs et les liens des matchs du jour."""
    async with session.get("https://tennisinsight.com/match-previews/") as resp:
        html = await resp.text()
    soup = BeautifulSoup(html, "lxml")
    tournaments = np.array([
        tour.text
        for tour in soup.find_all(class_="heading-link")
        if any(keyword in tour.text for keyword in ["ATP", "WTA", "Masters"])
    ])
    match_urls = [
        link_row.a["href"]
        for link_row in soup.find_all(class_="match-row-link")
        if link_row.a and link_row.a.has_attr("href")
    ]
    return tournaments, match_urls


def determine_elo_data(match_url: str, atp_elo: str, wta_elo: str) -> str:
    """Ordonne les tables ELO selon le circuit (ATP vs WTA)."""
    url_low = match_url.lower()
    if "atp" in url_low or ("wta" not in url_low and "masters" in url_low):
        return f"{atp_elo}\n{wta_elo}"
    return f"{wta_elo}\n{atp_elo}"


async def _process_single_match(
    match_url: str, tournaments: Sequence[str], elo_data: str, ctx: BatchContext
) -> Optional[str]:
    async with ctx.semaphore:
        match_info = await ctx.processor.process(match_url, tournaments, elo_data)
        if match_info:
            async with ctx.lock:
                ctx.results.append(match_info)
                if ctx.repository:
                    all_matchs = "\n".join(ctx.results) + "\n"
                    ctx.repository.save_processed_match(match_info, all_matchs)
        await asyncio.sleep(0.5)
        return match_info


async def process_matches(
    session: aiohttp.ClientSession,
    session_config: SessionConfig,
    tournaments: Sequence[str],
    match_urls: List[str],
    atp_elo: str = "",
    wta_elo: str = "",
    repository: Optional[MatchRepository] = None,
    max_parallel_matches: int = 5,
) -> str:
    """Traite la liste des matchs en parallèle sous contrôle de débit."""
    already = repository.load_reviewed_urls() if repository else set()
    processor = MatchProcessor(
        session, session_config.header, session_config.rate_limit, already
    )
    ctx = BatchContext(
        processor=processor,
        semaphore=asyncio.Semaphore(max_parallel_matches),
        repository=repository,
        lock=asyncio.Lock(),
        results=[],
    )

    batch_start = time.perf_counter()
    tasks = [
        _process_single_match(
            url, tournaments, determine_elo_data(url, atp_elo, wta_elo), ctx
        )
        for url in match_urls
    ]
    await asyncio.gather(*tasks)

    total_elapsed = round(time.perf_counter() - batch_start, 2)
    count = len(ctx.results)
    avg_per_match = round(total_elapsed / count, 2) if count > 0 else 0.0
    print(f"\n{'=' * 55}")
    print(f"Total processing time : {total_elapsed} sec ({count} match(s) processed)")
    print(f"Average time per match: {avg_per_match} sec/match")
    print(f"{'=' * 55}\n")

    return ("\n".join(ctx.results) + "\n") if ctx.results else ""


def _notify_daily_results(matchs_str: str) -> None:
    total_matches = len([line for line in (matchs_str or "").split("\n") if line.strip()])
    bets = get_session_bets()
    send_daily_email(bets, total_matches=total_matches)


async def main() -> None:
    """Point d'entrée principal du pipeline."""
    session_config = create_session_config()
    repository = MatchRepository()

    async with aiohttp.ClientSession(
        connector=session_config.connector,
        headers=session_config.header,
        timeout=session_config.timeout,
    ) as session:
        atp_elo, wta_elo = await asyncio.gather(
            elo_table("ATP", session=session),
            elo_table("WTA", session=session),
        )
        await login(session)
        tournaments, match_urls = await fetch_match_previews(session)
        matchs = await process_matches(
            session=session,
            session_config=session_config,
            tournaments=tournaments,
            match_urls=match_urls,
            atp_elo=atp_elo,
            wta_elo=wta_elo,
            repository=repository,
            max_parallel_matches=5,
        )

    print(matchs)
    _notify_daily_results(matchs)


if __name__ == "__main__":
    asyncio.run(main())