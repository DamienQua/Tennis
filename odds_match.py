"""
Asynchronously fetch and process betting odds for two players from Odds Portal.

This module provides functions to:
- Fetch odds data for a player from Odds Portal website
- Extract player name and odds from HTML content
- Process and compare odds between two players
- Update match and indices data based on retrieved odds

The main function `odds_match` retrieves odds for two players, compares their odds,
and updates match statistics accordingly.

Functions:
- fetch_odds: Retrieves HTML content for a player from Odds Portal
- extract_data: Parses HTML to extract player name and odds
- process_odds: Processes odds and updates match data
- odds_match: Orchestrates odds retrieval and processing for a match
"""

import os
os.environ.pop('SSLKEYLOGFILE', None)
import aiohttp
import asyncio
import re

async def fetch_odds(session, player):
    url = f"https://www.oddsportal.com/search/{player}"
    max_retries = 3
    delay = 0.25

    for attempt in range(max_retries):
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.text()
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
        except Exception:
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
    
    return ""

def _extract_match_name(text):
    home = re.search(r'(?:&quot;|\\")home-name(?:&quot;|\\"):(?:&quot;|\\")([^\\"]+)(?:&quot;|\\")', text)
    away = re.search(r'(?:&quot;|\\")away-name(?:&quot;|\\"):(?:&quot;|\\")([^\\"]+)(?:&quot;|\\")', text)
    if home and away:
        return f"{home.group(1)} - {away.group(1)}"
    
    match_name = re.search(r'(?:&quot;|\\")name(?:&quot;|\\"):(?:&quot;|\\")([A-Z][^\\"]*?\s*-\s*[^\\"]+?)(?:&quot;|\\")', text)
    if match_name:
        return match_name.group(1)
        
    html_players = re.findall(r'<p class="order-[12][^"]*">([^<]+)</p>', text)
    return f"{html_players[0]} - {html_players[1]}" if len(html_players) >= 2 else None

def _extract_odds_values(text):
    odds = re.findall(r'(?:&quot;|\\")maxOdds(?:&quot;|\\"):([\d.]+)', text)
    if not odds:
        odds = re.findall(r'class="font-primary font-bold">([\d.]+)</p>', text)
    if not odds:
        odds = re.findall(r'(?:&quot;|\\")avgOdds(?:&quot;|\\"):([\d.]+)', text)
    return (odds[0], odds[1]) if len(odds) >= 2 else (None, None)

def extract_data(text):
    name = _extract_match_name(text)
    odds1, odds2 = _extract_odds_values(text)
    return name, odds1, odds2

def _assign_player_odds(name, odds, match_vs):
    p1 = match_vs[2].split(" ")[-1].lower()
    p2 = match_vs[3].split(" ")[-1].lower()
    p1_pos = name.lower().find(p1)
    p2_pos = name.lower().find(p2)

    if p1_pos != -1 and (p2_pos == -1 or p1_pos < p2_pos):
        match_vs[38], match_vs[39] = odds[0], odds[1]
    else:
        match_vs[38], match_vs[39] = odds[1], odds[0]

def _update_odds_indices(match_vs, indice_tab):
    o1, o2 = float(match_vs[38]), float(match_vs[39])
    if o1 < o2:
        indice_tab[20], indice_tab[21] = 20, 0
    elif o1 > o2:
        indice_tab[20], indice_tab[21] = 0, 20
    else:
        indice_tab[20], indice_tab[21] = 10, 10

async def process_odds(html, match_vs, indice_tab, player_index):
    name, odds1, odds2 = extract_data(html)
    if not (name and odds1 and odds2):
        return False
    
    odds = [float(odds1), float(odds2)]
    _assign_player_odds(name, odds, match_vs)
    _update_odds_indices(match_vs, indice_tab)
    return True

async def fetch_both_odds(session, player1_name, player2_name):
    p1 = player1_name.split(" ")[-1] if player1_name else ""
    p2 = player2_name.split(" ")[-1] if player2_name else ""
    return await asyncio.gather(
        fetch_odds(session, p1),
        fetch_odds(session, p2)
    )

async def apply_odds_data(html1, html2, match_vs, indice_tab):
    success = await process_odds(html1, match_vs, indice_tab, 2)
    if not success:
        await process_odds(html2, match_vs, indice_tab, 3)
    
    oA = float(match_vs[36]) if match_vs[36] else 0.0
    oB = float(match_vs[37]) if match_vs[37] else 0.0
    if oA < oB:
        indice_tab[22], indice_tab[23] = 40, 0
    elif oA > oB:
        indice_tab[22], indice_tab[23] = 0, 40
    else:
        indice_tab[22], indice_tab[23] = 20, 20

    return match_vs, indice_tab

async def _odds_match_impl(session, match_vs, indice_tab, odds_future=None):
    if odds_future is not None:
        html1, html2 = await odds_future
    else:
        html1, html2 = await fetch_both_odds(session, match_vs[2], match_vs[3])
    
    return await apply_odds_data(html1, html2, match_vs, indice_tab)

async def odds_match(match_vs, indice_tab, session=None, odds_future=None):
    if session is not None:
        return await _odds_match_impl(session, match_vs, indice_tab, odds_future=odds_future)
    async with aiohttp.ClientSession() as new_session:
        return await _odds_match_impl(new_session, match_vs, indice_tab, odds_future=odds_future)