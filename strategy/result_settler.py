"""Vérification automatique des résultats, forfaits/abandons et CLV."""

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional, Tuple
import unicodedata
import aiohttp
from bs4 import BeautifulSoup
from core.models import MatchAnalysisData, PlayerStats
from core.player_extractor import PlayerExtractor
from data_providers.odds_match import odds_match

if TYPE_CHECKING:
    from core.database import TennisDatabase

logger = logging.getLogger(__name__)

_LIVE_MARKERS = ("in progress", "live now", "live score")
_CHAR_TRANSLATION = str.maketrans({
    "ł": "l",
    "Ł": "l",
    "đ": "d",
    "Đ": "d",
    "ø": "o",
    "Ø": "o",
    "ß": "ss",
})


def _normalize_text(text: str) -> str:
    """Supprime les accents/diacritiques et normalise la casse et les espaces."""
    translated = (text or "").translate(_CHAR_TRANSLATION)
    decomposed = unicodedata.normalize("NFKD", translated)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).strip().lower()


def _player_variants(player_name: str) -> Tuple[str, ...]:
    """Retourne les variantes normalisées (nom complet, alias, nom de famille)."""
    raw = (player_name or "").strip()
    if not raw:
        return ()
    alias = PlayerExtractor.PLAYER_ALIASES.get(raw, raw)
    candidates = []
    for name in (raw, alias):
        norm = _normalize_text(name)
        if norm and norm not in candidates:
            candidates.append(norm)
        parts = norm.split()
        if len(parts) >= 2:
            surname = parts[-1]
            if len(surname) >= 3 and surname not in candidates:
                candidates.append(surname)
    return tuple(candidates)


def _name_in_segment(player_name: str, segment: str) -> bool:
    norm_seg = _normalize_text(segment)
    for variant in _player_variants(player_name):
        if re.search(rf"\b{re.escape(variant)}\b", norm_seg):
            return True
    return False


def _extract_match_header_text(html: str) -> str:
    """Isole le bloc d'en-tête du match en excluant l'historique H2H."""
    soup = BeautifulSoup(html, "lxml")
    for h2h_block in soup.find_all(class_="h2h-matches"):
        h2h_block.decompose()
    header = soup.find(class_="match-preview-header") or soup.find("h1")
    if header and header.parent:
        return header.parent.get_text(" ", strip=True)
    return soup.get_text(" ", strip=True)[:2000]


def _is_match_live(header_text: str) -> bool:
    """Détecte si la rencontre est actuellement en cours afin de préserver la CLV pré-match."""
    low = header_text.lower()
    return any(marker in low for marker in _LIVE_MARKERS)


def _is_void_outcome(header_text: str) -> bool:
    """Détecte un forfait (w/o) ou un abandon avant la fin du 1er set."""
    low = header_text.lower()
    if "w/o" in low or "walkover" in low:
        return True
    if "ret." in low or "retired" in low:
        completed_sets = re.findall(r"\b(?:6-[0-4]|7-[56]|[0-4]-6|[56]-7)\b", header_text)
        return len(completed_sets) == 0
    return False


def _extract_fallback_winner(before_segment: str) -> Optional[str]:
    """Extrait le nom Unicode du vainqueur juste avant 'def.'/'defeated'."""
    cleaned = re.sub(r"[\(\[][^)\]]*[\)\]]", " ", before_segment).strip()
    match_name = re.search(
        r"([^\W\d_][\w'\-\.]*(?:\s+[^\W\d_][\w'\-\.]*){0,3})\s*$",
        cleaned,
        flags=re.UNICODE,
    )
    return match_name.group(1).strip() if match_name else None


def _parse_match_outcome(
    html: str, player_a: str = "", player_b: str = ""
) -> Tuple[Optional[str], bool]:
    """Retourne (nom_vainqueur, is_void) si le match est terminé, sinon (None, False)."""
    header_text = _extract_match_header_text(html)
    def_match = re.search(
        r"\b(?:def\.(?=\s|$)|defeated\b)", header_text, flags=re.IGNORECASE
    )
    if not def_match:
        return None, False

    before = header_text[:def_match.start()].strip()
    after = header_text[def_match.end():].strip()
    is_void = _is_void_outcome(header_text)

    if player_a and player_b:
        a_before = _name_in_segment(player_a, before[-120:])
        b_before = _name_in_segment(player_b, before[-120:])
        a_after = _name_in_segment(player_a, after[:120])
        b_after = _name_in_segment(player_b, after[:120])

        if a_before and (b_after or not b_before):
            return player_a, is_void
        if b_before and (a_after or not a_before):
            return player_b, is_void

    winner = _extract_fallback_winner(before[-120:])
    if not winner:
        return None, False
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
    is_p1 = _normalize_text(bet["selected_player"]) == _normalize_text(bet["player_a"])
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

        header_text = _extract_match_header_text(html)
        winner, is_void = _parse_match_outcome(
            html, player_a=bet.get("player_a", ""), player_b=bet.get("player_b", "")
        )
        if winner:
            db.settle_bet(url, winner, is_void=is_void)
            status_lbl = (
                "Remboursé (w/o ou ret. 1er set)" if is_void else f"Vainqueur : {winner}"
            )
            logger.info("Résultat mis à jour : %s -> %s", url, status_lbl)
            return True

        if not _is_match_live(header_text):
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
