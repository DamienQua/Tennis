"""Récupération asynchrone des cotes bookmakers depuis OddsPortal."""

import asyncio
import re
from typing import Optional, Tuple
import aiohttp
from core.models import MatchAnalysisData


async def fetch_odds(session: aiohttp.ClientSession, player: str) -> str:
    """Télécharge la page de recherche OddsPortal pour un joueur."""
    if not player:
        return ""
    url = f"https://www.oddsportal.com/search/{player}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=2.0)) as resp:
            if resp.status == 200:
                return await resp.text()
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        pass
    return ""


def _extract_match_name(text: str) -> Optional[str]:
    pattern_home = r'(?:&quot;|\\")home-name(?:&quot;|\\"):(?:&quot;|\\")([^\\"]+)(?:&quot;|\\")'
    pattern_away = r'(?:&quot;|\\")away-name(?:&quot;|\\"):(?:&quot;|\\")([^\\"]+)(?:&quot;|\\")'
    home = re.search(pattern_home, text)
    away = re.search(pattern_away, text)
    if home and away:
        return f"{home.group(1)} - {away.group(1)}"

    pat_name = (
        r'(?:&quot;|\\")name(?:&quot;|\\"):'
        r'(?:&quot;|\\")([A-Z][^\\"]*?\s*-\s*[^\\"]+?)(?:&quot;|\\")'
    )
    match_name = re.search(pat_name, text)
    if match_name:
        return match_name.group(1)

    html_players = re.findall(r'<p class="order-[12][^"]*">([^<]+)</p>', text)
    return f"{html_players[0]} - {html_players[1]}" if len(html_players) >= 2 else None


def _extract_odds_values(text: str) -> Tuple[Optional[str], Optional[str]]:
    odds = re.findall(r'(?:&quot;|\\")maxOdds(?:&quot;|\\"):([\d.]+)', text)
    if not odds:
        odds = re.findall(r'class="font-primary font-bold">([\d.]+)</p>', text)
    if not odds:
        odds = re.findall(r'(?:&quot;|\\")avgOdds(?:&quot;|\\"):([\d.]+)', text)
    return (odds[0], odds[1]) if len(odds) >= 2 else (None, None)


def extract_data(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extrait l'intitulé du match et les deux cotes."""
    if not text:
        return None, None, None
    name = _extract_match_name(text)
    odds1, odds2 = _extract_odds_values(text)
    return name, odds1, odds2


def _assign_player_odds(
    match_title: str, odds: Tuple[float, float], match: MatchAnalysisData
) -> bool:
    """Vérifie que les DEUX joueurs sont présents dans le titre avant assignation."""
    title_low = match_title.lower()
    p1_last = match.player_a.name.split()[-1].lower()
    p2_last = match.player_b.name.split()[-1].lower()

    p1_pos = title_low.find(p1_last)
    p2_pos = title_low.find(p2_last)
    if p1_pos == -1 or p2_pos == -1:
        return False

    if p1_pos < p2_pos:
        match.player_a.book_odds, match.player_b.book_odds = odds[0], odds[1]
    else:
        match.player_a.book_odds, match.player_b.book_odds = odds[1], odds[0]
    return True


def _update_odds_indices(match: MatchAnalysisData) -> None:
    odds_1, odds_2 = match.player_a.book_odds, match.player_b.book_odds
    if odds_1 < odds_2:
        match.confidence.book_fav_bonus = (20.0, 0.0)
    elif odds_1 > odds_2:
        match.confidence.book_fav_bonus = (0.0, 20.0)
    else:
        match.confidence.book_fav_bonus = (10.0, 10.0)


def process_odds(html: str, match: MatchAnalysisData) -> bool:
    """Parse et applique les cotes bookmakers au match si valides."""
    name, odds1, odds2 = extract_data(html)
    if not (name and odds1 and odds2):
        return False
    if not _assign_player_odds(name, (float(odds1), float(odds2)), match):
        return False
    _update_odds_indices(match)
    return True


async def fetch_both_odds(
    session: aiohttp.ClientSession, player1_name: str, player2_name: str
) -> Tuple[str, str]:
    """Tente le joueur 1 en priorité et court-circuite la 2e requête si trouvé."""
    surname_1 = player1_name.split()[-1] if player1_name else ""
    surname_2 = player2_name.split()[-1] if player2_name else ""
    html1 = await fetch_odds(session, surname_1)
    name, odds1, odds2 = extract_data(html1)
    if name and odds1 and odds2:
        return html1, ""
    html2 = await fetch_odds(session, surname_2)
    return html1, html2


def apply_odds_data(html1: str, html2: str, match: MatchAnalysisData) -> MatchAnalysisData:
    """Applique les cotes bookmakers et met à jour le bonus favori modèle."""
    if not process_odds(html1, match):
        process_odds(html2, match)

    odds_a, odds_b = match.player_a.model_odds, match.player_b.model_odds
    if odds_a < odds_b:
        match.confidence.model_fav_bonus = (40.0, 0.0)
    elif odds_a > odds_b:
        match.confidence.model_fav_bonus = (0.0, 40.0)
    else:
        match.confidence.model_fav_bonus = (20.0, 20.0)
    return match


async def odds_match(
    match: MatchAnalysisData,
    session: Optional[aiohttp.ClientSession] = None,
    odds_future: Optional[asyncio.Future] = None,
) -> MatchAnalysisData:
    """Orchestre la récupération et l'application des cotes bookmakers."""
    if odds_future is not None:
        html1, html2 = await odds_future
        return apply_odds_data(html1, html2, match)

    if session is not None:
        html1, html2 = await fetch_both_odds(
            session, match.player_a.name, match.player_b.name
        )
        return apply_odds_data(html1, html2, match)

    async with aiohttp.ClientSession() as new_session:
        html1, html2 = await fetch_both_odds(
            new_session, match.player_a.name, match.player_b.name
        )
        return apply_odds_data(html1, html2, match)