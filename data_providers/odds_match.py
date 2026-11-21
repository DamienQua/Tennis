"""Cotes OddsPortal : identité complète et statut prématch explicite requis."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
import json
import math
import re
from typing import Iterator, List, Optional, Tuple
from urllib.parse import quote

import aiohttp
from core.models import MatchAnalysisData
from utils.http_client import request
from utils.player_identity import names_match


class _OddsPage(str):
    """Conserve l'instant de réception même si l'analyse est différée."""

    def __new__(cls, text: str):
        instance = super().__new__(cls, text)
        instance.observed_at = datetime.now(timezone.utc).isoformat()
        return instance


async def fetch_odds(session: aiohttp.ClientSession, player: str) -> str:
    if not player:
        return ""
    url = f"https://www.oddsportal.com/search/{quote(player, safe='')}/tennis/"
    try:
        async with request(
            session, "GET", url, timeout=aiohttp.ClientTimeout(total=2.0)
        ) as response:
            if response.status == 200:
                return _OddsPage(await response.text())
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        pass
    return ""


class _JSONObject(list):
    """Préserve les clés maxOdds répétées dans certains documents intégrés."""

    def values_for(self, key: str) -> list:
        return [value for name, value in self if name == key]

    def first(self, key: str, default=None):
        values = self.values_for(key)
        return values[0] if values else default


def _walk_objects(value, depth: int = 0) -> Iterator[_JSONObject]:
    if isinstance(value, _JSONObject):
        yield value
        for _, child in value:
            yield from _walk_objects(child, depth)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_objects(child, depth)
    elif isinstance(value, str) and "{" in value:
        yield from _json_objects(value, depth + 1)


def _json_objects(text: str, depth: int = 0) -> Iterator[_JSONObject]:
    """Décode des objets complets, sans mélanger les champs de deux rencontres."""
    source = unescape(text)
    if depth > 3:
        return
    decoder = json.JSONDecoder(object_pairs_hook=_JSONObject)
    cursor = 0
    while True:
        start = source.find("{", cursor)
        if start == -1:
            return
        try:
            value, end = decoder.raw_decode(source, start)
        except (ValueError, RecursionError):
            # JSON.stringify / chaîne JavaScript : décoder une couche complète
            # conserve les accents Unicode et les échappements dans les noms.
            if start > 0 and source[start - 1] == '"':
                try:
                    decoded, end = decoder.raw_decode(source, start - 1)
                    if isinstance(decoded, str):
                        yield from _json_objects(decoded, depth + 1)
                        cursor = end
                        continue
                except (ValueError, RecursionError):
                    pass
            # Fragment échappé sans guillemets extérieurs, fréquent en attribut HTML.
            if source[start:].startswith('{\\"'):
                try:
                    decoded, _ = decoder.raw_decode(source[start:].replace('\\"', '"'))
                    yield from _walk_objects(decoded, depth)
                except (ValueError, RecursionError):
                    pass
            cursor = start + 1
            continue
        yield from _walk_objects(value, depth)
        cursor = end


def _flag_enabled(value) -> bool:
    return value is True or value == 1 or (
        isinstance(value, str) and value.strip().casefold() in {"true", "1"}
    )


def _market_status(event: _JSONObject) -> str:
    if any(_flag_enabled(value) for name, value in event
           if name.casefold() in ("isfinished", "isended")):
        return "finished"
    if any(_flag_enabled(value) for name, value in event
           if name.casefold() in ("islive", "inplay", "isstarted")):
        return "live"
    if any(_flag_enabled(value) for name, value in event
           if name.casefold() in ("issuspended", "isclosed")):
        return "unknown"
    statuses = [
        re.sub(r"[^a-z]", "", str(value).casefold())
        for name, value in event
        if name.casefold() in ("status", "eventstatus", "matchstatus")
    ]
    finished = {"finished", "ended", "completed", "cancelled", "canceled", "walkover"}
    live = {"live", "inplay", "inprogress", "started"}
    if any(status in finished for status in statuses):
        return "finished"
    if any(status in live for status in statuses):
        return "live"
    prematch = {"prematch", "scheduled", "upcoming", "notstarted"}
    return "prematch" if statuses and all(status in prematch for status in statuses) else "unknown"


def _scheduled_start(event: _JSONObject) -> str:
    starts = set()
    for key in ("scheduledStart", "startTime", "startTimestamp", "startDate"):
        for value in event.values_for(key):
            try:
                if isinstance(value, bool):
                    return ""
                if isinstance(value, (int, float)):
                    timestamp = value / 1000 if value > 100_000_000_000 else value
                    parsed = datetime.fromtimestamp(timestamp, timezone.utc)
                elif isinstance(value, str):
                    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if parsed.tzinfo is None or parsed.utcoffset() is None:
                        return ""
                else:
                    return ""
            except (ValueError, OverflowError, OSError):
                return ""
            starts.add(parsed.astimezone(timezone.utc).isoformat())
    return starts.pop() if len(starts) == 1 else ""


def _price(value) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and result > 1.0 else None


def _side(label, home: str, away: str) -> Optional[int]:
    if not isinstance(label, str):
        return None
    if label.casefold() in ("1", "home") or names_match(label, home):
        return 0
    if label.casefold() in ("2", "away") or names_match(label, away):
        return 1
    return None


def _price_pair(value, home: str, away: str) -> Optional[Tuple[float, float]]:
    if not isinstance(value, list) or len(value) != 2:
        return None
    if isinstance(value, _JSONObject):
        ordered = {}
        for label, price in value:
            side = _side(label, home, away)
            if side is None or side in ordered:
                return None
            ordered[side] = _price(price)
        values = [ordered.get(0), ordered.get(1)]
    else:
        values = [_price(price) for price in value]
    return tuple(values) if all(price is not None for price in values) else None


def _is_winner_market(obj: _JSONObject) -> bool:
    labels = [str(value).casefold().replace(" ", "").replace("-", "")
              for name, value in obj
              if name in ("name", "marketName", "marketType", "market", "type")]
    periods = [str(value).casefold().replace(" ", "") for name, value in obj
               if name in ("period", "scope")]
    return (
        any(label in {"matchwinner", "matchresult", "moneyline", "1x2", "h2h"}
            for label in labels)
        and not any(re.search(r"set|game|handicap|total|overunder", label) for label in labels)
        and all(period in {"match", "fullmatch", "fulltime"} for period in periods)
    )


def _market_unavailable(market: _JSONObject) -> bool:
    if any(_flag_enabled(value) for key, value in market
           if key.casefold() in ("issuspended", "isclosed", "isfinished", "isended",
                                 "islive", "inplay", "isstarted")):
        return True
    statuses = [re.sub(r"[^a-z]", "", str(value).casefold())
                for key, value in market if key.casefold() == "status"]
    if any(status not in {"open", "active", "prematch", "scheduled", "upcoming", "notstarted"}
           for status in statuses):
        return True
    return False


def _market_prices(market: _JSONObject, home: str, away: str) -> Optional[Tuple[float, float]]:
    """Les deux prix restent dans le même marché, avec ordre des issues vérifié."""
    if _market_unavailable(market):
        return None
    for key in ("maxOdds", "avgOdds", "odds"):
        values = market.values_for(key)
        if values:
            return _price_pair(values[0] if len(values) == 1 else values, home, away)
    outcomes = market.first("outcomes", market.first("selections"))
    if not isinstance(outcomes, list) or isinstance(outcomes, _JSONObject) or len(outcomes) != 2:
        return None
    ordered = {}
    for outcome in outcomes:
        if not isinstance(outcome, _JSONObject) or _market_unavailable(outcome):
            return None
        labels = [value for name, value in outcome if name in ("name", "label", "side")]
        sides = {_side(label, home, away) for label in labels}
        if len(sides) != 1 or None in sides:
            return None
        side = sides.pop()
        if side in ordered:
            return None
        for key in ("maxOdds", "avgOdds", "odds", "price"):
            values = outcome.values_for(key)
            if values:
                if len(values) != 1:
                    return None
                ordered[side] = _price(values[0])
                break
    prices = (ordered.get(0), ordered.get(1))
    return prices if all(price is not None for price in prices) else None


def _odds_values(event: _JSONObject, home: str, away: str) -> Optional[Tuple[float, float]]:
    def scoped_objects(value, root=False):
        if isinstance(value, _JSONObject):
            if not root and (value.values_for("home-name") or value.values_for("away-name")):
                return
            yield value
            for _, child in value:
                yield from scoped_objects(child)
        elif isinstance(value, list):
            for child in value:
                yield from scoped_objects(child)

    markets = [obj for obj in scoped_objects(event, root=True) if _is_winner_market(obj)]
    if not markets:
        return None
    # Plusieurs bookmakers/instantanés ne sont pas agrégés implicitement.
    candidates = {_market_prices(market, home, away) for market in markets}
    return candidates.pop() if len(candidates) == 1 else None


@dataclass(frozen=True)
class _OddsEvent:
    home: str
    away: str
    odds: Optional[Tuple[float, float]]
    status: str
    scheduled_start: str
    event_id: str


def _events(text: str) -> Iterator[_OddsEvent]:
    now = datetime.now(timezone.utc)
    for obj in _json_objects(text):
        home_values, away_values = obj.values_for("home-name"), obj.values_for("away-name")
        if not home_values or not away_values:
            continue
        status = _market_status(obj)
        start = _scheduled_start(obj)
        has_schedule = any(key in {"scheduledStart", "startTime", "startTimestamp", "startDate"}
                           for key, _ in obj)
        identity_valid = len(home_values) == len(away_values) == 1
        if not identity_valid or (has_schedule and not start):
            status = "unknown"
        elif status == "prematch" and start and datetime.fromisoformat(start) <= now:
            status = "unknown"
        identifier = str(obj.first("eventId", obj.first("id", "")))
        for home in home_values:
            for away in away_values:
                if not isinstance(home, str) or not isinstance(away, str) or names_match(home, away):
                    continue
                if "/" in home or "/" in away:
                    continue
                odds = _odds_values(obj, home, away) if identity_valid else None
                yield _OddsEvent(home, away, odds, status, start, identifier)


def _matches_event(event: _OddsEvent, player_a: str, player_b: str) -> Optional[bool]:
    """True : ordre direct ; False : inversé ; None : identités non concordantes."""
    if names_match(event.home, player_a) and names_match(event.away, player_b):
        return True
    if names_match(event.home, player_b) and names_match(event.away, player_a):
        return False
    return None


def _extract_json_events(text: str) -> List[Tuple[str, str, str]]:
    return [
        (f"{event.home} - {event.away}", str(event.odds[0]), str(event.odds[1]))
        for event in _events(text)
        if event.status == "prematch" and event.odds is not None
    ]


def extract_data(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Ne récupère jamais des cotes brutes après le rejet du statut d'un événement."""
    events = _extract_json_events(text)
    return events[0] if len(events) == 1 else (None, None, None)


def _target_events(html: str, player_a: str, player_b: str) -> List[_OddsEvent]:
    return list(dict.fromkeys(event for event in _events(html)
                            if _matches_event(event, player_a, player_b) is not None))


def _update_odds_indices(match: MatchAnalysisData) -> None:
    odds_1, odds_2 = match.player_a.book_odds, match.player_b.book_odds
    if odds_1 < odds_2:
        match.confidence.book_fav_bonus = (20.0, 0.0)
    elif odds_1 > odds_2:
        match.confidence.book_fav_bonus = (0.0, 20.0)
    else:
        match.confidence.book_fav_bonus = (10.0, 10.0)


def process_odds(html: str, match: MatchAnalysisData) -> bool:
    """Applique uniquement les cotes d'une rencontre identifiée, explicitement prématch."""
    match.player_a.book_odds = match.player_b.book_odds = 0.0
    match.confidence.book_fav_bonus = (0.0, 0.0)
    match.market_status = "unknown"
    match.odds_observed_at = ""
    match.scheduled_start = ""
    events = _target_events(html, match.player_a.name, match.player_b.name)
    if len(events) != 1:
        return False
    event = events[0]
    match.market_status = event.status
    match.scheduled_start = event.scheduled_start
    if event.status != "prematch" or event.odds is None:
        return False
    now = datetime.now(timezone.utc)
    try:
        observed = datetime.fromisoformat(getattr(html, "observed_at", now.isoformat()))
        if observed.tzinfo is None or observed.utcoffset() is None or observed > now:
            return False
    except (TypeError, ValueError, OverflowError):
        return False
    direct_order = _matches_event(event, match.player_a.name, match.player_b.name)
    odds = event.odds if direct_order else event.odds[::-1]
    match.player_a.book_odds, match.player_b.book_odds = odds
    match.odds_observed_at = observed.astimezone(timezone.utc).isoformat()
    _update_odds_indices(match)
    return True


async def fetch_both_odds(
    session: aiohttp.ClientSession, player1_name: str, player2_name: str
) -> Tuple[str, str]:
    """Le second joueur sert uniquement à retrouver une rencontre absente."""
    surname_1 = player1_name.split()[-1] if player1_name else ""
    surname_2 = player2_name.split()[-1] if player2_name else ""
    html1 = await fetch_odds(session, surname_1)
    if _target_events(html1, player1_name, player2_name):
        return html1, ""
    html2 = await fetch_odds(session, surname_2)
    return html1, html2


def apply_odds_data(html1: str, html2: str, match: MatchAnalysisData) -> MatchAnalysisData:
    source = html1
    if not _target_events(html1, match.player_a.name, match.player_b.name) and html2:
        source = html2
    process_odds(source, match)
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
    if odds_future is not None:
        html1, html2 = await odds_future
        return apply_odds_data(html1, html2, match)
    if session is not None:
        html1, html2 = await fetch_both_odds(session, match.player_a.name, match.player_b.name)
        return apply_odds_data(html1, html2, match)
    async with aiohttp.ClientSession() as new_session:
        html1, html2 = await fetch_both_odds(new_session, match.player_a.name, match.player_b.name)
        return apply_odds_data(html1, html2, match)
