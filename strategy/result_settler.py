"""Vérification automatique des résultats, forfaits/abandons et CLV."""

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional, Tuple
import aiohttp
from bs4 import BeautifulSoup
from core.models import MatchAnalysisData, PlayerStats
from data_providers.odds_match import odds_match

if TYPE_CHECKING:
    from core.database import TennisDatabase

logger = logging.getLogger(__name__)


def _extract_match_header_text(html: str) -> str:
    """Isole le bloc d'en-tête du match en excluant l'historique H2H."""
    soup = BeautifulSoup(html, "lxml")
    for h2h_block in soup.find_all(class_="h2h-matches"):
        h2h_block.decompose()
    header = soup.find(class_="match-preview-header") or soup.find("h1")
    if header and header.parent:
        return header.parent.get_text(" ", strip=True)
    return soup.get_text(" ", strip=True)[:2000]


def _is_void_outcome(header_text: str) -> bool:
    """Détecte un forfait (w/o) ou un abandon avant la fin du 1er set."""
    low = header_text.lower()
    if "w/o" in low or "walkover" in low:
        return True
    if "ret." in low or "retired" in low:
        completed_sets = re.findall(r"\b(?:6-[0-4]|7-[56]|[0-4]-6|[56]-7)\b", header_text)
        return len(completed_sets) == 0
    return False


def _parse_match_outcome(html: str) -> Tuple[Optional[str], bool]:
    """Retourne (nom_vainqueur, is_void) si le match est terminé, sinon (None, False)."""
    header_text = _extract_match_header_text(html)
    match_def = re.search(
        r"([A-Z][a-zA-Z\s\-']+?)\s+(?:def\.|defeated)\s+[A-Z]", header_text
    )
    if not match_def:
        return None, False
    winner = match_def.group(1).strip()
    is_void = _is_void_outcome(header_text)
    return winner, is_void


async def _refresh_clv_for_pending(
    session: aiohttp.ClientSession, db: "TennisDatabase", bet: dict
) -> None:
    """Met à jour la cote de clôture et la CLV tant que le match n'a pas débuté."""
    temp_match = MatchAnalysisData(
        match_url=bet["match_url"],
        player_a=PlayerStats(name=bet["player_a"]),
        player_b=PlayerStats(name=bet["player_b"]),
    )
    await odds_match(temp_match, session=session)
    is_p1 = bet["selected_player"].lower() == bet["player_a"].lower()
    latest_odds = temp_match.player_a.book_odds if is_p1 else temp_match.player_b.book_odds
    if latest_odds > 1.0:
        db.update_closing_odds(bet["match_url"], latest_odds)


async def _check_single_bet(
    session: aiohttp.ClientSession, db: "TennisDatabase", bet: dict
) -> bool:
    url = bet["match_url"]
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return False
            html = await resp.text()

        winner, is_void = _parse_match_outcome(html)
        if winner:
            db.settle_bet(url, winner, is_void=is_void)
            status_lbl = "Remboursé (w/o ou ret. 1er set)" if is_void else f"Vainqueur : {winner}"
            logger.info("Résultat mis à jour : %s -> %s", url, status_lbl)
            return True

        await _refresh_clv_for_pending(session, db, bet)
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
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
    print(
        f"Bilan ROI : {roi_stats['settled']} pari(s) réglé(s) | "
        f"Winrate : {roi_stats['winrate']}% | Profit : {roi_stats['profit']:+.2f}u | "
        f"ROI : {roi_stats['roi']:+.2f}% | CLV Moy : {roi_stats['avg_clv']:+.2f}%"
    )
    return settled_count