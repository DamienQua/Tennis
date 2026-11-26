"""Point d'entrée principal du pipeline asynchrone d'analyse de matchs de tennis."""

import argparse
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import os
import time
from typing import Dict, List, NamedTuple, Optional, Sequence, Set, Tuple
import aiohttp
from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from dotenv import dotenv_values
import numpy as np

from core.analyze_match import analyze_match, clear_session_bets, get_session_bets
from core.database import TennisDatabase
from core.match_filter import MatchFilter
from core.models import MatchAnalysisData
from data_providers.elo_finder import elo_table
from strategy.email_notifier import send_daily_email
from strategy.result_settler import update_pending_results
from utils.helpers import fetch_with_retry

os.environ.pop("SSLKEYLOGFILE", None)
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            "logs/tennis_ai.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        ),
    ],
)
logger = logging.getLogger(__name__)

LOGIN_URL = "https://tennisinsight.com/wp-login.php"
_RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}
_HARD_CREDENTIAL_MARKERS = (
    "incorrect",
    "invalid username",
    "invalid email",
    "unknown username",
    "unknown email",
    "not registered",
    "password you entered",
)


class TennisInsightOutageError(RuntimeError):
    """Indique une indisponibilité transitoire du serveur TennisInsight (5xx/timeout)."""


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
        db: Optional[TennisDatabase] = None,
        match_filter: Optional[MatchFilter] = None,
    ) -> None:
        self.session = session
        self.header = header
        self.rate_limit = rate_limit
        self.already_processed = already_processed
        self.db = db
        self.filter = match_filter or MatchFilter()

    def should_process(self, match_url: str) -> bool:
        return self.filter.should_process(match_url, self.already_processed)

    async def fetch_and_analyze(
        self, match_url: str, tournaments: Sequence[str], elo_data: str
    ) -> Optional[MatchAnalysisData]:
        async with self.rate_limit:
            return await analyze_match(
                self.session, self.header, match_url, tournaments, elo_data, db=self.db
            )

    @staticmethod
    def format_result(match_info: str, match_url: str) -> str:
        return f"{match_info}, {match_url}"

    async def process(
        self,
        match_url: str,
        tournaments: Sequence[str],
        elo_data: str,
        max_retries: int = 2,
    ) -> Optional[MatchAnalysisData]:
        """Exécute l'analyse complète d'un match avec gestion des erreurs temporaires."""
        if not self.should_process(match_url):
            return None

        for attempt in range(max_retries):
            start = time.perf_counter()
            try:
                match_data = await self.fetch_and_analyze(match_url, tournaments, elo_data)
                if not match_data:
                    return None
                self.finalize_result(match_data.to_summary_line(), match_url, start)
                return match_data
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
        logger.info("Match : %s (%.2fs)", result, raw_elapsed)
        return result


class BatchContext:
    """Contexte partagé d'exécution concurrente."""

    def __init__(
        self,
        processor: MatchProcessor,
        semaphore: asyncio.Semaphore,
        db: Optional[TennisDatabase],
        lock: asyncio.Lock,
        results: List[str],
    ) -> None:
        self.processor = processor
        self.semaphore = semaphore
        self.db = db
        self.lock = lock
        self.results = results


def create_session_config(
    max_concurrent: int = 6, timeout_seconds: float = 30.0
) -> SessionConfig:
    """Initialise les paramètres de la session HTTP (ménage le serveur WordPress/MySQL)."""
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    header = {"User-Agent": user_agent}
    conn = aiohttp.TCPConnector(limit=max_concurrent)
    rate_limit = AsyncLimiter(4, 1)
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


def _has_wordpress_auth_cookie(
    session: aiohttp.ClientSession, response: aiohttp.ClientResponse
) -> bool:
    """Vérifie la présence d'un cookie de session WordPress (réponse, redirections, cookie_jar)."""
    responses = [response, *(getattr(response, "history", ()) or ())]
    for resp_item in responses:
        resp_cookies = getattr(resp_item, "cookies", None) or {}
        if any(str(name).startswith("wordpress_logged_in_") for name in resp_cookies):
            return True

    jar = getattr(session, "cookie_jar", None)
    if jar is not None:
        for cookie in jar:
            if getattr(cookie, "key", "").startswith("wordpress_logged_in_"):
                return True
    return False


def _extract_login_diagnostics(
    session: aiohttp.ClientSession,
    response: aiohttp.ClientResponse,
    body_html: str,
) -> Tuple[str, str]:
    """Extrait (message_login_error, resume_diagnostic) sans exposer les valeurs de cookies."""
    soup = BeautifulSoup(body_html or "", "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    err_elem = soup.find(id="login_error")
    login_error = err_elem.get_text(" ", strip=True) if err_elem else ""

    jar = getattr(session, "cookie_jar", None)
    cookie_names = sorted({
        getattr(c, "key", "") for c in (jar or []) if getattr(c, "key", "")
    })
    summary = (
        f"status={getattr(response, 'status', '?')}, "
        f"url={getattr(response, 'url', LOGIN_URL)}, "
        f"title={title!r}, "
        f"cookies={cookie_names}"
    )
    if login_error:
        summary += f", login_error={login_error!r}"
    return login_error, summary


def _is_hard_credential_error(login_error: str) -> bool:
    low = (login_error or "").lower()
    return any(marker in low for marker in _HARD_CREDENTIAL_MARKERS)


async def _fetch_login_hidden_fields(
    session: aiohttp.ClientSession, timeout: aiohttp.ClientTimeout
) -> Dict[str, str]:
    """Effectue un GET préalable sur wp-login.php pour récupérer testcookie et champs cachés."""
    hidden_fields: Dict[str, str] = {}
    async with session.get(LOGIN_URL, timeout=timeout) as get_resp:
        get_resp.raise_for_status()
        html = await get_resp.text()
    soup = BeautifulSoup(html or "", "lxml")
    form = soup.find("form", id="loginform") or soup.find("form", attrs={"name": "loginform"})
    if form:
        for inp in form.find_all("input", attrs={"type": "hidden"}):
            name = inp.get("name")
            if name:
                hidden_fields[name] = inp.get("value", "")
    return hidden_fields


async def login(
    session: aiohttp.ClientSession,
    max_retries: int = 5,
    base_delay: float = 5.0,
) -> None:
    """Authentifie la session sur TennisInsight sans suivre la redirection vers l'accueil."""
    config = dotenv_values(".env") if os.path.exists(".env") else {}
    username = _get_credential(config, "TENNISINSIGHT_LOGIN")
    password = _get_credential(config, "TENNISINSIGHT_PASSWORD")
    if not username or not password:
        raise ValueError(
            "Les identifiants TENNISINSIGHT_LOGIN et TENNISINSIGHT_PASSWORD "
            "doivent être définis dans l'environnement ou le fichier .env."
        )

    login_timeout = aiohttp.ClientTimeout(total=45.0, connect=15.0)
    post_headers = {
        "Referer": LOGIN_URL,
        "Origin": "https://tennisinsight.com",
    }
    cached_hidden_fields: Optional[Dict[str, str]] = None

    for attempt in range(max_retries):
        try:
            if cached_hidden_fields is None:
                cached_hidden_fields = await _fetch_login_hidden_fields(session, login_timeout)

            payload = dict(cached_hidden_fields)
            payload.update({
                "log": username,
                "pwd": password,
                "wp-submit": "Log In",
                "rememberme": "forever",
                "testcookie": "1",
            })

            async with session.post(
                LOGIN_URL,
                data=payload,
                headers=post_headers,
                timeout=login_timeout,
                allow_redirects=False,
            ) as resp:
                resp.raise_for_status()
                if _has_wordpress_auth_cookie(session, resp):
                    logger.info("Authentification TennisInsight vérifiée avec succès.")
                    return

                body_html = await resp.text()
                login_error, diag = _extract_login_diagnostics(session, resp, body_html)
                err_msg = (
                    "Échec d'authentification TennisInsight : "
                    f"cookie wordpress_logged_in_* absent ({diag})."
                )
                if _is_hard_credential_error(login_error):
                    raise RuntimeError(err_msg)
                if attempt >= max_retries - 1:
                    raise TennisInsightOutageError(err_msg)

                cached_hidden_fields = None
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "Login sans cookie (%d/%d : %s). Nouvelle tentative dans %.0fs...",
                    attempt + 1,
                    max_retries,
                    diag,
                    delay,
                )
                await asyncio.sleep(delay)
        except (
            aiohttp.ClientResponseError,
            aiohttp.ClientError,
            TimeoutError,
            asyncio.TimeoutError,
            OSError,
        ) as err:
            is_non_retryable_http = (
                isinstance(err, aiohttp.ClientResponseError)
                and err.status not in _RETRYABLE_HTTP_STATUSES
            )
            if is_non_retryable_http:
                raise
            if attempt >= max_retries - 1:
                raise TennisInsightOutageError(
                    f"TennisInsight indisponible après {max_retries} tentatives : {err}"
                ) from err
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "Échec transitoire login TennisInsight (%d/%d : %s). Nouvelle tentative dans %.0fs...",
                attempt + 1,
                max_retries,
                err,
                delay,
            )
            await asyncio.sleep(delay)


async def fetch_match_previews(session: aiohttp.ClientSession) -> Tuple[np.ndarray, List[str]]:
    """Récupère les tournois actifs et les liens des matchs du jour avec reprises réseau."""
    html = await fetch_with_retry(
        session,
        "https://tennisinsight.com/match-previews/",
        method="GET",
        attempts=3,
        backoff_step=2.0,
    )
    if not html:
        raise TennisInsightOutageError(
            "Impossible de récupérer match-previews sur TennisInsight."
        )
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
        match_data = await ctx.processor.process(match_url, tournaments, elo_data)
        if match_data:
            line = f"{match_data.to_summary_line()}, {match_url}"
            async with ctx.lock:
                ctx.results.append(line)
                if ctx.db:
                    ctx.db.save_match(match_data)
        await asyncio.sleep(0.5)
        return match_data.to_summary_line() if match_data else None


async def process_matches(
    session: aiohttp.ClientSession,
    session_config: SessionConfig,
    tournaments: Sequence[str],
    match_urls: List[str],
    atp_elo: str = "",
    wta_elo: str = "",
    db: Optional[TennisDatabase] = None,
    max_parallel_matches: int = 2,
) -> str:
    """Traite la liste des matchs en parallèle sous contrôle de débit."""
    clear_session_bets()
    if os.path.exists("Matchs.txt"):
        os.remove("Matchs.txt")

    already = db.load_reviewed_urls() if db else set()
    processor = MatchProcessor(
        session, session_config.header, session_config.rate_limit, already, db=db
    )
    ctx = BatchContext(
        processor=processor,
        semaphore=asyncio.Semaphore(max_parallel_matches),
        db=db,
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
    logger.info(
        "Batch terminé : %d match(s) en %.2fs (moyenne %.2fs/match)",
        count,
        total_elapsed,
        avg_per_match,
    )

    return ("\n".join(ctx.results) + "\n") if ctx.results else ""


def _notify_daily_results(matchs_str: str, excel_path: str) -> None:
    total_matches = len([line for line in (matchs_str or "").split("\n") if line.strip()])
    bets = get_session_bets()
    send_daily_email(bets, total_matches=total_matches, filepath=excel_path)


def _parse_cli_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline d'analyse de matchs de tennis")
    parser.add_argument(
        "--update-results",
        action="store_true",
        help="Vérifie et met à jour uniquement les résultats des paris en attente",
    )
    parser.add_argument(
        "--with-update-results",
        action="store_true",
        help="Met à jour les résultats en attente puis lance l'analyse dans la même session",
    )
    parser.add_argument(
        "--soft-fail-on-outage",
        action="store_true",
        help="Quitte proprement (code 0, sans e-mail) en cas de panne 5xx/timeout TennisInsight",
    )
    return parser.parse_args(argv)


def _handle_outage(err: TennisInsightOutageError, soft_fail: bool) -> None:
    if not soft_fail:
        raise err
    logger.warning(
        "Panne transitoire TennisInsight (%s). Arrêt propre (--soft-fail-on-outage), "
        "aucun e-mail quotidien envoyé.",
        err,
    )
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning title=TennisInsight indisponible::{err}")


async def main(argv: Optional[Sequence[str]] = None) -> None:
    """Point d'entrée principal du pipeline."""
    args = _parse_cli_args(argv)
    db = TennisDatabase()

    if args.update_results and not db.get_pending_bets():
        logger.info("Aucun pari en attente de résultat : authentification ignorée.")
        return

    session_config = create_session_config()
    try:
        async with aiohttp.ClientSession(
            connector=session_config.connector,
            headers=session_config.header,
            timeout=session_config.timeout,
        ) as session:
            await login(session)

            if args.update_results:
                await update_pending_results(session, db)
                return

            if args.with_update_results and db.get_pending_bets():
                try:
                    await update_pending_results(session, db)
                except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError, OSError) as err:
                    logger.warning(
                        "Mise à jour des résultats en échec transitoire (%s), poursuite de l'analyse.",
                        err,
                    )

            atp_elo, wta_elo = await asyncio.gather(
                elo_table("ATP", session=session),
                elo_table("WTA", session=session),
            )
            tournaments, match_urls = await fetch_match_previews(session)
            matchs = await process_matches(
                session=session,
                session_config=session_config,
                tournaments=tournaments,
                match_urls=match_urls,
                atp_elo=atp_elo,
                wta_elo=wta_elo,
                db=db,
                max_parallel_matches=2,
            )
    except TennisInsightOutageError as err:
        _handle_outage(err, soft_fail=args.soft_fail_on_outage)
        return

    excel_path = db.export_bets_to_excel()
    if matchs:
        print(matchs)
    _notify_daily_results(matchs, excel_path=excel_path)


if __name__ == "__main__":
    asyncio.run(main())
