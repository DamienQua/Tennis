"""Vérification automatique des résultats, forfaits/abandons et CLV."""

import asyncio
from datetime import datetime, timezone
import logging
import math
import re
from typing import TYPE_CHECKING, Optional, Tuple
import aiohttp
from bs4 import BeautifulSoup
from core.models import MatchAnalysisData, PlayerStats
from data_providers.odds_match import odds_match
from utils.http_client import request
from utils.player_identity import names_match

if TYPE_CHECKING:
    from core.database import TennisDatabase

logger = logging.getLogger(__name__)


def _extract_match_header_text(html: str) -> str:
    """Isole le bloc d'en-tête du match en excluant l'historique H2H."""
    soup = BeautifulSoup(html, "lxml")
    for h2h_block in soup.find_all(class_="h2h-matches"):
        h2h_block.decompose()
    header = soup.find(class_="match-preview-header") or soup.find("h1")
    if not header:
        return ""
    return header.get_text(" ", strip=True)


def _has_retirement(header_text: str) -> bool:
    return bool(re.search(r"\b(?:ret\.|retired)\b|\bret\.(?=\s|$)", header_text, re.I))


def _set_scores(header_text: str) -> list[tuple[int, int]]:
    return [
        (int(a), int(b))
        for a, b in re.findall(r"(?<![\w-])(\d{1,2})\s*[-–]\s*(\d{1,2})(?![\w-])", header_text)
    ]


def _is_void_outcome(header_text: str) -> bool:
    """Détecte un forfait (w/o) ou un abandon avant la fin du 1er set."""
    if re.search(r"\b(?:w\s*/\s*o|walkover)\b", header_text, re.I):
        return True
    if _has_retirement(header_text):
        scores = _set_scores(header_text)
        completed = any(
            (max(a, b) >= 6 and abs(a - b) >= 2) or {a, b} == {6, 7}
            for a, b in scores
        )
        # Sans score, il est impossible de déterminer si un set a été terminé.
        return bool(scores) and not completed
    return False


def _resolve_participant(text: str, players: tuple[str, str], *, suffix: bool) -> Optional[str]:
    """Accepte une identité connue, jamais un simple patronyme deviné."""
    candidate = text.strip()
    if suffix:
        candidate = re.sub(r"^Final\s*:?\s+", "", candidate, flags=re.I)
    else:
        # Seuls les scores et statuts explicites délimitent la fin du nom.
        # Tronquer mot par mot confondrait, par exemple, un joueur et son homonyme Junior.
        candidate = re.split(
            r"\s+(?=\d{1,2}\s*[-–]\s*\d{1,2}\b|ret\.(?:\s|$)|retired\b|w\s*/\s*o\b|walkover\b)",
            candidate, maxsplit=1, flags=re.I,
        )[0]
    matches = [player for player in players if player and names_match(candidate, player)]
    return matches[0] if len(matches) == 1 else None


def _parse_match_outcome(
    html: str, player_a: str = "", player_b: str = ""
) -> Tuple[Optional[str], bool]:
    """Retourne une identité certaine ou un remboursement, sinon garde le pari en attente."""
    header_text = _extract_match_header_text(html)
    outcomes = list(re.finditer(
        r"\s+(def\.|defeated|vs\.?|v\.|w\s*/\s*o|walkover)\s+", header_text, re.I,
    ))
    if len(outcomes) != 1 or not player_a or not player_b:
        return None, False
    outcome = outcomes[0]
    players = (player_a, player_b)
    winner = _resolve_participant(header_text[:outcome.start()], players, suffix=True)
    loser = _resolve_participant(header_text[outcome.end():], players, suffix=False)
    if not winner or not loser or names_match(winner, loser):
        return None, False
    if _is_void_outcome(header_text):
        return None, True
    if _has_retirement(header_text) and not _set_scores(header_text):
        return None, False
    if outcome.group(1).lower() not in {"def.", "defeated"}:
        return None, False
    return winner, False


def _valid_prematch_observation(match: MatchAnalysisData) -> bool:
    if match.market_status != "prematch":
        return False
    try:
        observed = datetime.fromisoformat(match.odds_observed_at)
        start = datetime.fromisoformat(match.scheduled_start)
    except (TypeError, ValueError):
        return False
    if observed.tzinfo is None or start.tzinfo is None:
        return False
    now = datetime.now(timezone.utc)
    return observed <= now < start and observed < start


async def _refresh_clv_for_pending(
    session: aiohttp.ClientSession, db: "TennisDatabase", bet: dict
) -> bool:
    """Met à jour la cote de clôture et la CLV tant que le match n'a pas débuté."""
    temp_match = MatchAnalysisData(
        match_url=bet["match_url"],
        player_a=PlayerStats(name=bet["player_a"]),
        player_b=PlayerStats(name=bet["player_b"]),
    )
    await odds_match(temp_match, session=session)
    if not _valid_prematch_observation(temp_match):
        return False
    selected = [
        names_match(bet["selected_player"], bet["player_a"]),
        names_match(bet["selected_player"], bet["player_b"]),
    ]
    if selected.count(True) != 1:
        return False
    is_p1 = selected[0]
    latest_odds = temp_match.player_a.book_odds if is_p1 else temp_match.player_b.book_odds
    if math.isfinite(latest_odds) and latest_odds > 1.0:
        return db.update_closing_odds(
            bet["match_url"], latest_odds,
            observed_at=temp_match.odds_observed_at,
            scheduled_start=temp_match.scheduled_start,
        )
    return False


async def _check_single_bet(
    session: aiohttp.ClientSession, db: "TennisDatabase", bet: dict
) -> bool:
    url = bet["match_url"]
    try:
        async with request(session, "GET", url) as resp:
            if resp.status != 200:
                return False
            html = await resp.text()

        winner, is_void = _parse_match_outcome(html, bet["player_a"], bet["player_b"])
        if winner or is_void:
            if not db.settle_bet(url, winner or "", is_void=is_void):
                return False
            status_lbl = "Remboursé (w/o ou ret. 1er set)" if is_void else f"Vainqueur : {winner}"
            logger.info("Résultat mis à jour : %s -> %s", url, status_lbl)
            return True

        await _refresh_clv_for_pending(session, db, bet)
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as err:
        logger.warning("Impossible de vérifier %s : %s", url, err)
    return False


async def update_pending_results(
    session: aiohttp.ClientSession, db: "TennisDatabase"
) -> int:
    """Parcourt les paris en attente, met à jour CLV et règle les matchs terminés."""
    pending = db.get_pending_bets()
    if not pending:
        print("Aucun pari en attente de résultat.")
        return 0

    results = await asyncio.gather(
        *(_check_single_bet(session, db, bet) for bet in pending)
    )
    settled_count = sum(1 for r in results if r)
    db.export_bets_to_excel()

    roi_stats = db.get_roi_summary()
    avg_clv = roi_stats['avg_clv']
    clv_label = "Indisponible" if avg_clv is None else f"{avg_clv:+.2f}%"
    print(
        f"Bilan ROI : {roi_stats['settled']} pari(s) réglé(s) | "
        f"Winrate : {roi_stats['winrate']}% | Profit : {roi_stats['profit']:+.2f}u | "
        f"ROI : {roi_stats['roi']:+.2f}% | CLV Moy : {clv_label}"
    )
    return settled_count
