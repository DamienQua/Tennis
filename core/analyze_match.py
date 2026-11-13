"""Orchestration asynchrone complète de l'analyse d'un match de tennis."""

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Sequence
import aiohttp
from bs4 import BeautifulSoup

from analysis.compare_indice import compare_indice
from analysis.compare_players import compare_players
from analysis.h2h_table import h2h_table, MatchContext
from analysis.indice_confiance import indice_confiance
from analysis.last_matchs import last_matchs
from core.models import MatchAnalysisData
from core.player_extractor import extract_player_ids, extract_player_names
from core.tournament_extractor import (
    determine_tournament_and_surface,
    parse_player_rankings,
    who_is_favorite,
)
from data_providers.elo_matcher import EloMatcher
from data_providers.odds_match import odds_match, fetch_both_odds
from strategy.alpha_strategy import evaluate_alpha_strategy
from strategy.alpha_tracker import record_alpha_selection
from strategy.generate_match_xlsx import generate_match_xlsx

logger = logging.getLogger(__name__)
ADMIN_URL = "https://tennisinsight.com/wp-admin/admin-ajax.php"


async def _attempt_fetch(
    session: aiohttp.ClientSession, url: str, method: str, data: Any
) -> Optional[str]:
    req = session.post(url, data=data) if method == "post" else session.get(url)
    async with req as response:
        if response.status == 200:
            return await response.text()
        return None


async def fetch_data(
    session: aiohttp.ClientSession, url: str, method: str = "get", data: Any = None
) -> str:
    """Exécute une requête HTTP avec tentatives de reprise."""
    for attempt in range(3):
        try:
            result = await _attempt_fetch(session, url, method, data)
            if result is not None:
                return result
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            pass
        if attempt < 2:
            await asyncio.sleep(1.0 * (attempt + 1))
    return ""


async def _fetch_match_soups(
    session: aiohttp.ClientSession, match_url: str
) -> Optional[Dict[str, Any]]:
    """Télécharge et parse la page principale et le panneau overview AJAX."""
    if not match_url or "match/" not in match_url:
        logger.warning("URL de match invalide : %s", match_url)
        return None
    parts = match_url.split("match/")[1].split("/")
    match_id = parts[0] if parts else ""
    if not match_id:
        return None

    overview_req = {"action": "lazyLoadPanes", "pane": "overview", "matchID": match_id}
    html_main, overview_html = await asyncio.gather(
        fetch_data(session, match_url),
        fetch_data(session, ADMIN_URL, "post", overview_req),
    )
    soup_main = BeautifulSoup(html_main, "lxml")
    soup_overview = BeautifulSoup(overview_html, "lxml")
    p_a_id, p_b_id = extract_player_ids(html_main, soup_main)
    if not p_a_id or not p_b_id:
        logger.warning("Identifiants joueurs introuvables pour %s", match_url)
        return None

    return {
        "match_id": match_id,
        "soup_main": soup_main,
        "soup_overview": soup_overview,
        "ids": (p_a_id, p_b_id),
    }


def _populate_metadata(
    match: MatchAnalysisData,
    tournaments: Sequence[str],
    soup_main: BeautifulSoup,
    soup_overview: BeautifulSoup,
) -> None:
    """Remplit les métadonnées tournoi, surface, noms et classements."""
    match.tournament, match.surface = determine_tournament_and_surface(
        match.match_url, tournaments
    )
    name_a, name_b = extract_player_names(
        soup_main, match.match_url, soup_overview.text
    )
    match.player_a.name = name_a
    match.player_b.name = name_b
    rankings = parse_player_rankings(soup_overview)
    match.player_a.ranking, match.player_b.ranking = rankings[0], rankings[1]


async def _run_analysis_phases(
    session: aiohttp.ClientSession,
    header: dict,
    parsed: Dict[str, Any],
    match: MatchAnalysisData,
) -> None:
    """Exécute motivation, forme récente et H2H en parallèle."""
    today = time.time()
    favorite = who_is_favorite(parsed["soup_overview"])
    id_a, id_b = parsed["ids"]
    m_id = parsed["match_id"]

    await asyncio.gather(
        indice_confiance(
            session=session,
            admin_url=ADMIN_URL,
            player_id=id_a,
            match_id=m_id,
            surface=match.surface,
            flag=0,
            choix="Motivation",
            confidence=match.confidence,
        ),
        indice_confiance(
            session=session,
            admin_url=ADMIN_URL,
            player_id=id_b,
            match_id=m_id,
            surface=match.surface,
            flag=1,
            choix="Motivation",
            confidence=match.confidence,
        ),
        last_matchs(session, today, match, ADMIN_URL, id_a, m_id, 0, favorite),
        last_matchs(session, today, match, ADMIN_URL, id_b, m_id, 1, favorite),
    )
    ctx = MatchContext(match.surface, ADMIN_URL, header, m_id)
    await h2h_table(parsed["soup_overview"], match, session, ctx)


def _evaluate_and_record_strategy(elo_data: str, match: MatchAnalysisData) -> None:
    """Associe les cotes ELO, évalue Alpha 5+ et enregistre la sélection."""
    elo_a, elo_b = EloMatcher.find_elo_ratings(
        elo_data, match.player_a.name, match.player_b.name, match.surface
    )
    if elo_a:
        match.player_a.elo = float(elo_a)
    if elo_b:
        match.player_b.elo = float(elo_b)

    alpha_res = evaluate_alpha_strategy(match)
    print(f"  {alpha_res['summary']}")
    record_alpha_selection(
        tournament=match.tournament,
        surface=match.surface,
        player1=match.player_a.name,
        player2=match.player_b.name,
        alpha_res=alpha_res,
        match_url=match.match_url,
    )


async def analyze_match(
    session: aiohttp.ClientSession,
    header: dict,
    match_url: str,
    tournaments: Sequence[str],
    elo_data: str,
) -> Optional[MatchAnalysisData]:
    """Point d'entrée complet d'analyse d'un match."""
    parsed = await _fetch_match_soups(session, match_url)
    if not parsed:
        return None

    match = MatchAnalysisData(match_url=match_url)
    _populate_metadata(match, tournaments, parsed["soup_main"], parsed["soup_overview"])

    odds_future = asyncio.create_task(
        fetch_both_odds(session, match.player_a.name, match.player_b.name)
    )
    await _run_analysis_phases(session, header, parsed, match)
    compare_players(match)
    await odds_match(match, session=session, odds_future=odds_future)
    compare_indice(match)
    _evaluate_and_record_strategy(elo_data, match)
    generate_match_xlsx(match)
    return match