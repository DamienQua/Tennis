"""
Analyzes a tennis match by fetching and processing various data points from an online source.

This async module coordinates comprehensive match analysis by:
- Delegating player and tournament extraction to specialized extractors
- Fetching player rankings and motivation indices
- Generating head-to-head statistics
- Comparing player performance
- Processing match odds and Elo ratings
- Generating a match report spreadsheet
"""

import asyncio
import time
from typing import Any, Dict, Optional

import aiohttp
from bs4 import BeautifulSoup
import numpy as np

from analysis.compare_indice import compare_indice
from analysis.compare_players import compare_players
from analysis.h2h_table import h2h_table, MatchContext
from analysis.indice_confiance import indice_confiance
from analysis.last_matchs import last_matchs
from core.player_extractor import (
    PlayerExtractor,
    clean_player_name,
    extract_player_ids,
    extract_player_names
)
from core.tournament_extractor import (
    TournamentExtractor,
    determine_tournament_and_surface,
    extract_tournament_slug,
    parse_player_rankings,
    who_is_favorite
)
from data_providers.elo_matcher import EloMatcher
from data_providers.odds_match import odds_match, fetch_both_odds
from strategy.alpha_strategy import evaluate_alpha_strategy
from strategy.alpha_tracker import record_alpha_selection
from strategy.generate_match_xlsx import generate_match_xlsx


async def _fetch_url_response(session, url: str, method: str, data: Any):
    if method == 'post':
        return await session.post(url, data=data)
    return await session.get(url)


async def _attempt_fetch(session, url: str, method: str, data: Any) -> Optional[str]:
    async with await _fetch_url_response(session, url, method, data) as response:
        if response.status == 200:
            return await response.text()
        return None


async def fetch_data(
        session: aiohttp.ClientSession,
        url: str,
        method: str = 'get',
        data: Any = None
) -> str:
    """Executes HTTP request to retrieve match preview or admin data."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            result = await _attempt_fetch(session, url, method, data)
            if result is not None:
                return result
            if attempt < max_retries - 1:
                await asyncio.sleep(1.0 * (attempt + 1))
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            if attempt < max_retries - 1:
                await asyncio.sleep(1.0 * (attempt + 1))
    return ""


async def _fetch_match_soups(
        session: aiohttp.ClientSession,
        match: str,
        admin_url: str
) -> Optional[Dict[str, Any]]:
    """Fetches and parses main page and overview AJAX pane for a match."""
    if not match or "match/" not in match:
        print(f"⚠️ URL de match invalide : {match}")
        return None
    parts = match.split("match/")[1].split("/")
    match_id = parts[0] if parts else ""
    if not match_id:
        return None
    overview_req = {"action": "lazyLoadPanes", "pane": "overview", "matchID": match_id}
    abc, overview_data = await asyncio.gather(
        fetch_data(session, match),
        fetch_data(session, admin_url, 'post', overview_req)
    )
    soup_abc = BeautifulSoup(abc, "lxml")
    data = BeautifulSoup(overview_data, "lxml")
    p_a_id, p_b_id = extract_player_ids(abc, soup_abc)
    if not p_a_id or not p_b_id:
        print(f"⚠️ Identifiants joueurs introuvables pour {match} - match ignoré.")
        return None
    return {
        "match_id": match_id,
        "soup_abc": soup_abc,
        "data": data,
        "ids": (p_a_id, p_b_id)
    }


def _populate_initial_metadata(
        match_vs: np.ndarray,
        match: str,
        tournaments: Any,
        soup_abc: BeautifulSoup,
        data: BeautifulSoup
) -> str:
    """Populates tournament, surface, players, and rankings into match vector."""
    tour, surface = determine_tournament_and_surface(match, tournaments)
    match_vs[0], match_vs[1] = tour, surface
    p_a, p_b = extract_player_names(soup_abc, match, data.text)
    match_vs[2], match_vs[3] = p_a, p_b
    rankings = parse_player_rankings(data)
    match_vs[4], match_vs[5] = rankings[0], rankings[1]
    return surface


async def _execute_analysis_phases(
        session: aiohttp.ClientSession,
        admin_url: str,
        header: dict,
        parsed: Dict[str, Any],
        surface: str,
        match_vs: np.ndarray,
        indice_tab: np.ndarray
) -> None:
    """Executes motivation, recent matches, and H2H analysis phases."""
    today = time.time()
    favorite = who_is_favorite(parsed["data"])
    ids = parsed["ids"]
    m_id = parsed["match_id"]
    await asyncio.gather(
        indice_confiance(
            session, admin_url, ids[0], m_id, surface, 0, "Motivation",
            indice_tab=indice_tab
        ),
        indice_confiance(
            session, admin_url, ids[1], m_id, surface, 1, "Motivation",
            indice_tab=indice_tab
        ),
        last_matchs(session, today, match_vs, admin_url, ids[0], m_id, 0, favorite),
        last_matchs(session, today, match_vs, admin_url, ids[1], m_id, 1, favorite)
    )
    ctx = MatchContext(surface, admin_url, header, m_id)
    await h2h_table(parsed["data"], match_vs, session, ctx, indice_tab=indice_tab)


def _evaluate_and_record_strategy(
        elo: str,
        match_vs: np.ndarray,
        surface: str,
        match: str
) -> None:
    """Computes Elo ratings, evaluates Alpha strategy, and records selection."""
    elo_a, elo_b = EloMatcher.find_elo_ratings(elo, match_vs[2], match_vs[3], surface)
    if elo_a.replace(".", "").isdigit():
        match_vs[40] = elo_a
    if elo_b.replace(".", "").isdigit():
        match_vs[41] = elo_b
    alpha_res = evaluate_alpha_strategy(
        match_vs[36], match_vs[37], match_vs[38], match_vs[39],
        match_vs[40], match_vs[41], match_vs[2], match_vs[3]
    )
    print(f"  {alpha_res['summary']}")
    record_alpha_selection(
        match_vs[0], match_vs[1], match_vs[2], match_vs[3], alpha_res, match
    )


def _format_match_summary(match_vs: np.ndarray, indice_tab: np.ndarray) -> str:
    """Formats the match vector and confidence index into final summary string."""
    return (
        ", ".join(match_vs[:4]) + ", " + ", ".join(match_vs[-8:-2]) +
        ", " + match_vs[15] + ", " + match_vs[26] + ", " + str(indice_tab[-1]) +
        ", " + match_vs[19] + ", " + match_vs[30]
    )


async def analyze_match(
        session: aiohttp.ClientSession,
        header: dict,
        match: str,
        tournaments: Any,
        elo: str
) -> str:
    """Main entry point orchestrating full match preview and analysis."""
    admin_url = "https://tennisinsight.com/wp-admin/admin-ajax.php"
    parsed = await _fetch_match_soups(session, match, admin_url)
    if not parsed:
        return ""

    match_vs = np.full(44, "", dtype="<U100")
    indice_tab = np.zeros(25)

    surface = _populate_initial_metadata(
        match_vs, match, tournaments, parsed["soup_abc"], parsed["data"]
    )
    odds_future = asyncio.create_task(fetch_both_odds(session, match_vs[2], match_vs[3]))

    await _execute_analysis_phases(
        session, admin_url, header, parsed, surface, match_vs, indice_tab
    )
    compare_players(match_vs)
    match_vs, indice_tab = await odds_match(
        match_vs, indice_tab, session=session, odds_future=odds_future
    )
    compare_indice(indice_tab, match_vs)

    _evaluate_and_record_strategy(elo, match_vs, surface, match)
    await generate_match_xlsx(match_vs)

    return _format_match_summary(match_vs, indice_tab)
