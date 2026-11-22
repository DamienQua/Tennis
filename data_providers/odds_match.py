"""Récupération asynchrone des cotes bookmakers depuis OddsPortal (Singles à venir)."""

import asyncio
import re
from typing import List, Optional, Tuple
from urllib.parse import quote
import aiohttp
from core.models import MatchAnalysisData
from utils.helpers import normalize_text

_Q = r'(?:&quot;|\\"|")'
_JSON_EVENT_RE = re.compile(rf"{_Q}home-name{_Q}")
ODDS_TIMEOUT_SECONDS = 6.0


def _extract_surname_and_initial(full_name: str) -> Tuple[str, str]:
    norm = normalize_text(full_name).replace("-", " ")
    parts = norm.split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], parts[0][0]


def _side_matches_player(side_text: str, full_name: str) -> bool:
    """Vérifie qu'un côté ('Home' ou 'Away') correspond au joueur par frontières de mots."""
    surname, first_init = _extract_surname_and_initial(full_name)
    if not surname:
        return False
    norm_side = normalize_text(side_text).replace("-", " ")
    if not re.search(rf"\b{re.escape(surname)}\b", norm_side):
        return False
    full_norm = normalize_text(full_name).replace("-", " ")
    if full_norm in norm_side:
        return True
    if first_init:
        side_tokens = [tok.rstrip(".") for tok in norm_side.split() if tok.rstrip(".") != surname]
        if side_tokens and not any(tok.startswith(first_init) for tok in side_tokens):
            return False
    return True


def _resolve_match_order(
    match_title: str, player_a_name: str, player_b_name: str
) -> Optional[bool]:
    """Retourne True si player_a est Home (gauche), False si player_a est Away, None sinon."""
    if not match_title or "/" in match_title:
        return None

    if " - " in match_title:
        left, right = match_title.split(" - ", 1)
        a_left = _side_matches_player(left, player_a_name)
        b_right = _side_matches_player(right, player_b_name)
        if a_left and b_right:
            return True
        a_right = _side_matches_player(right, player_a_name)
        b_left = _side_matches_player(left, player_b_name)
        if a_right and b_left:
            return False
        return None

    norm_title = normalize_text(match_title).replace("-", " ")
    sur_a, _ = _extract_surname_and_initial(player_a_name)
    sur_b, _ = _extract_surname_and_initial(player_b_name)
    if not sur_a or not sur_b or sur_a == sur_b:
        return None

    m_a = re.search(rf"\b{re.escape(sur_a)}\b", norm_title)
    m_b = re.search(rf"\b{re.escape(sur_b)}\b", norm_title)
    if not (m_a and m_b):
        return None
    return m_a.start() < m_b.start()


async def fetch_odds(
    session: aiohttp.ClientSession,
    player: str,
    timeout_seconds: float = ODDS_TIMEOUT_SECONDS,
) -> str:
    """Télécharge la page de recherche OddsPortal pour un joueur."""
    clean_query = normalize_text(player)
    if not clean_query:
        return ""
    encoded = quote(clean_query, safe="")
    url = f"https://www.oddsportal.com/search/{encoded}/tennis/"
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout_seconds)
        ) as resp:
            if resp.status == 200:
                return await resp.text()
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        pass
    return ""


def _is_finished_chunk(chunk: str) -> bool:
    """Détecte si un bloc événement correspond à un match déjà terminé ou live."""
    low = chunk.lower()
    return (
        '"isfinished":true' in low
        or '&quot;isfinished&quot;:true' in low
        or '"status":"finished"' in low
        or '&quot;status&quot;:&quot;finished&quot;' in low
        or '"islive":true' in low
        or '&quot;islive&quot;:true' in low
    )


def _has_json_events(text: str) -> bool:
    return bool(text and _JSON_EVENT_RE.search(text))


def _extract_json_events(text: str) -> List[Tuple[str, str, str]]:
    """Extrait les événements (titre, cote1, cote2) pré-match depuis le JSON intégré."""
    events: List[Tuple[str, str, str]] = []
    chunks = re.split(rf"(?={_Q}home-name{_Q})", text)
    pat_home = rf"{_Q}home-name{_Q}:{_Q}([^{{\}}\"\\]+){_Q}"
    pat_away = rf"{_Q}away-name{_Q}:{_Q}([^{{\}}\"\\]+){_Q}"

    for chunk in chunks[1:]:
        if _is_finished_chunk(chunk[:2500]):
            continue
        home = re.search(pat_home, chunk)
        away = re.search(pat_away, chunk)
        if not (home and away):
            continue
        title = f"{home.group(1)} - {away.group(1)}"
        if "/" in title:
            continue
        odds1, odds2 = _extract_odds_values(chunk[:8000])
        if odds1 and odds2:
            events.append((title, odds1, odds2))
    return events


def _extract_match_name(text: str) -> Optional[str]:
    pat_name = rf"{_Q}name{_Q}:{_Q}([A-Z][^{{\}}\"\\]*?\s*-\s*[^{{\}}\"\\]+?){_Q}"
    match_name = re.search(pat_name, text)
    if match_name:
        return match_name.group(1)

    html_players = re.findall(r'<p class="order-[12][^"]*">([^<]+)</p>', text)
    return f"{html_players[0]} - {html_players[1]}" if len(html_players) >= 2 else None


def _extract_odds_values(text: str) -> Tuple[Optional[str], Optional[str]]:
    odds = re.findall(rf"{_Q}maxOdds{_Q}:([\d.]+)", text)
    if not odds:
        odds = re.findall(r'class="font-primary font-bold">([\d.]+)</p>', text)
    if not odds:
        odds = re.findall(rf"{_Q}avgOdds{_Q}:([\d.]+)", text)
    return (odds[0], odds[1]) if len(odds) >= 2 else (None, None)


def extract_data(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extrait l'intitulé du match simple à venir et les deux cotes (jamais de match terminé)."""
    if not text:
        return None, None, None
    if _has_json_events(text):
        events = _extract_json_events(text)
        return events[0] if events else (None, None, None)

    if _is_finished_chunk(text):
        return None, None, None
    name = _extract_match_name(text)
    if name and "/" in name:
        return None, None, None
    odds1, odds2 = _extract_odds_values(text)
    return name, odds1, odds2


def _html_contains_pair(html: str, player1_name: str, player2_name: str) -> bool:
    """Vérifie qu'un HTML OddsPortal contient bien le match pré-match exact entre les deux joueurs."""
    if not html:
        return False
    if _has_json_events(html):
        for title, odds1, odds2 in _extract_json_events(html):
            if odds1 and odds2 and _resolve_match_order(title, player1_name, player2_name) is not None:
                return True
        return False

    name, odds1, odds2 = extract_data(html)
    if name and odds1 and odds2:
        return _resolve_match_order(name, player1_name, player2_name) is not None
    return False


def _assign_player_odds(
    match_title: str, odds: Tuple[float, float], match: MatchAnalysisData
) -> bool:
    """Vérifie que c'est un simple (pas de '/') et que les DEUX joueurs correspondent."""
    a_is_first = _resolve_match_order(
        match_title, match.player_a.name, match.player_b.name
    )
    if a_is_first is None:
        return False

    if a_is_first:
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
    """Parse et applique les cotes bookmakers au match si valides et non terminées."""
    if not html:
        return False

    if _has_json_events(html):
        for title, odds1, odds2 in _extract_json_events(html):
            if _assign_player_odds(title, (float(odds1), float(odds2)), match):
                _update_odds_indices(match)
                return True
        return False

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
    """Tente le joueur 1 en priorité et court-circuite uniquement si la paire exacte est trouvée."""
    surname_1 = player1_name.split()[-1] if player1_name else ""
    surname_2 = player2_name.split()[-1] if player2_name else ""
    html1 = await fetch_odds(session, surname_1)
    if _html_contains_pair(html1, player1_name, player2_name):
        return html1, ""
    if normalize_text(surname_2) == normalize_text(surname_1):
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
