"""Vérification automatique des résultats de matchs terminés sur TennisInsight."""

import asyncio
import logging
import re
from typing import Optional
import aiohttp
from bs4 import BeautifulSoup
from core.database import TennisDatabase

logger = logging.getLogger(__name__)


def _extract_winner_from_html(html: str) -> Optional[str]:
    """Extrait le nom du vainqueur si le match est terminé ('def.' ou 'defeated')."""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    match_def = re.search(r"([A-Z][a-zA-Z\s\-']+?)\s+(?:def\.|defeated)\s+[A-Z]", text)
    if match_def:
        return match_def.group(1).strip()
    return None


async def _check_single_bet(
    session: aiohttp.ClientSession, db: TennisDatabase, bet: dict
) -> bool:
    url = bet["match_url"]
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return False
            html = await resp.text()
        winner = _extract_winner_from_html(html)
        if winner:
            db.settle_bet(url, winner)
            logger.info("Résultat mis à jour : %s -> Vainqueur : %s", url, winner)
            return True
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        logger.warning("Impossible de vérifier %s : %s", url, err)
    return False


async def update_pending_results(
    session: aiohttp.ClientSession, db: TennisDatabase
) -> int:
    """Parcourt les paris en attente et met à jour les matchs terminés."""
    pending = db.get_pending_bets()
    if not pending:
        print("Aucun pari en attente de résultat.")
        return 0

    results = await asyncio.gather(
        *(_check_single_bet(session, db, bet) for bet in pending)
    )
    settled_count = sum(1 for r in results if r)
    if settled_count > 0:
        db.export_bets_to_excel()

    roi_stats = db.get_roi_summary()
    print(
        f"Bilan ROI : {roi_stats['settled']} pari(s) réglé(s) | "
        f"Winrate : {roi_stats['winrate']}% | Profit : {roi_stats['profit']:+.2f}u | "
        f"ROI : {roi_stats['roi']:+.2f}%"
    )
    return settled_count