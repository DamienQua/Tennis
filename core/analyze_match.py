"""
Analyzes a tennis match by fetching and processing various data points from an online source.

This async function performs a comprehensive match analysis by:
- Extracting player IDs and match details
- Determining tournament and surface
- Fetching player rankings and motivation indices
- Generating head-to-head statistics
- Comparing player performance
- Processing match odds
- Extracting Elo ratings
- Generating a match report spreadsheet

Args:
    session: Aiohttp client session for making async HTTP requests
    header: Request headers
    match: URL of the match to analyze
    tournaments: List of tournament names
    elo: Elo ratings data

Returns:
    str: A summary of key match details including tournament, surface, players, 
         and various performance indicators
"""

import asyncio
import re
from bs4 import BeautifulSoup
import time
import numpy as np
import jaro
from analysis.h2h_table import h2h_table, MatchContext
from analysis.last_matchs import last_matchs
from analysis.compare_players import compare_players
from data_providers.odds_match import odds_match, fetch_both_odds
from analysis.indice_confiance import indice_confiance
from analysis.compare_indice import compare_indice
from strategy.generate_match_xlsx import generate_match_xlsx
from data_providers.elo_matcher import EloMatcher
from strategy.alpha_strategy import evaluate_alpha_strategy
from strategy.alpha_tracker import record_alpha_selection

async def _fetch_url_response(session, url, method, data):
    if method == 'post':
        return await session.post(url, data=data)
    return await session.get(url)

async def _attempt_fetch(session, url, method, data):
    async with await _fetch_url_response(session, url, method, data) as response:
        if response.status == 200:
            return await response.text()
        return None

async def fetch_data(session, url, method='get', data=None):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            result = await _attempt_fetch(session, url, method, data)
            if result is not None:
                return result
            if attempt < max_retries - 1:
                await asyncio.sleep(1.0 * (attempt + 1))
        except Exception:
            if attempt < max_retries - 1:
                await asyncio.sleep(1.0 * (attempt + 1))
    return ""

def _ids_from_soup(soup_abc):
    if not soup_abc:
        return []
    seen = []
    for a in soup_abc.find_all('a', href=re.compile(r'/player/\?playerid=\d+')):
        m = re.search(r'playerid=(\d+)', a.get('href', ''))
        if m and m.group(1) not in seen and 'General Comments' not in a.text:
            seen.append(m.group(1))
    return seen

def _ids_from_regex(abc):
    raw = re.findall(r'/player/\?playerid=(\d+)', abc)
    if len(raw) < 2:
        raw = re.findall(r'playerid=(\d+)', abc)
    seen = []
    for pid in raw:
        if pid not in seen:
            seen.append(pid)
    return seen

def extract_player_ids(abc, soup_abc=None):
    ids = _ids_from_soup(soup_abc)
    if len(ids) < 2 and isinstance(abc, str):
        ids = _ids_from_regex(abc)
    pA_id = ids[0] if len(ids) > 0 else ""
    pB_id = ids[1] if len(ids) > 1 else ""
    return pA_id, pB_id

def clean_player_name(name):
    cleaned = re.sub(r'^\s*[\(\[][A-Za-z0-9/]+[\)\]]\s*', '', name.strip())
    cleaned = cleaned.replace("-Vinolas", "").replace(" Vitus Nodskov", "").strip()
    if cleaned == "Cori Gauff":
        return "Coco Gauff"
    return cleaned

def _names_from_title(soup_abc):
    titles = soup_abc.find_all(class_="profile-title")
    if len(titles) >= 2:
        pA = clean_player_name(titles[0].text)
        pB = clean_player_name(titles[1].text)
        if pA and pB:
            return pA, pB
    return None

def _names_from_links(soup_abc):
    players = []
    seen_ids = set()
    for a in soup_abc.find_all('a', href=re.compile(r'/player/\?playerid=\d+')):
        pid = a.get('href', '').split('playerid=')[-1]
        text = a.text.strip()
        if pid not in seen_ids and text and 'General Comments' not in text:
            seen_ids.add(pid)
            players.append(clean_player_name(text))
    return (players[0], players[1]) if len(players) >= 2 else None

def _names_from_overview(data_text):
    for_parts = data_text.split("for ")
    if len(for_parts) >= 3:
        pA = clean_player_name(for_parts[1].split("\n")[0])
        pB = clean_player_name(for_parts[2].split("\n")[0])
        if pA and pB:
            return pA, pB
    return None

def _names_from_slug(match_url):
    parts = [p for p in match_url.split('/') if p]
    match_slug = parts[-1] if parts else ""
    if '-vs-' in match_slug:
        p1_slug, p2_slug = match_slug.split('-vs-')[:2]
        return p1_slug.replace('-', ' ').title(), p2_slug.replace('-', ' ').title()
    return None

def extract_player_names(soup_abc, match_url, data_text=""):
    return (
        _names_from_title(soup_abc)
        or _names_from_links(soup_abc)
        or _names_from_overview(data_text)
        or _names_from_slug(match_url)
        or ("Player A", "Player B")
    )

def extract_tournament_slug(match_url):
    found = re.search(r'/\d{4}-([^/]+)/', match_url)
    if found:
        return found.group(1)
    parts = [p for p in match_url.split("/") if p]
    return parts[-2] if len(parts) >= 2 else match_url

def determine_tournament_and_surface(match, tournaments):
    slug = extract_tournament_slug(match)
    if tournaments is not None and len(tournaments) > 0:
        t_list = list(tournaments)
        same_tour = np.zeros(len(t_list), float)
        for i, tourn in enumerate(t_list):
            same_tour[i] = jaro.jaro_winkler_metric(slug, tourn.split(" (")[0].lower())
        best_idx = int(same_tour.argmax(0))
        tour_str = t_list[best_idx]
        tour = tour_str.split(" (")[0]
        surface = tour_str.split("- ")[1].split(" Court")[0] if "- " in tour_str else "Clay"
        return tour, surface
    clean_tour = slug.replace("-", " ").title()
    return clean_tour, "Clay"

def parse_player_rankings(data):
    rankings = []
    for i in range(2):
        try:
            ranking = int(data.text.replace("Unknown","1000").split("(HI")[i].split("\n")[-1].strip())
        except:
            ranking = 1000
        rankings.append(ranking)
    return rankings

def who_is_favorite(data):
    try :
        if float(data.find(class_="mp_bio_left").find_all("li")[-1].text.strip()) > float(data.find(class_="mp_bio_right").find_all("li")[-1].text.strip()):
            return [1, 0]
        else:
            return [0, 1]
    except:
        return [0, 0]

async def analyze_match(session, header, match, tournaments, elo):
    today = time.time()
    indice_tab = np.zeros(25)
    match_vs = np.full(44, "", dtype="<U100")
    admin_url = "https://tennisinsight.com/wp-admin/admin-ajax.php"

    match_id = match.split("match/")[1].split("/")[0]

    abc, overview_data = await asyncio.gather(
        fetch_data(session, match),
        fetch_data(session, admin_url, 'post', {"action": "lazyLoadPanes", "pane": "overview", "matchID": match_id})
    )
    soup_abc = BeautifulSoup(abc, "lxml")
    data = BeautifulSoup(overview_data, "lxml")
    pA_id, pB_id = extract_player_ids(abc, soup_abc)

    if not pA_id or not pB_id:
        print(f"⚠️ Identifiants joueurs introuvables pour {match} - match ignoré.")
        return ""

    tour, surface = determine_tournament_and_surface(match, tournaments)
    match_vs[0] = tour
    match_vs[1] = surface

    pA, pB = extract_player_names(soup_abc, match, data.text)
    match_vs[2], match_vs[3] = pA, pB

    odds_future = asyncio.create_task(fetch_both_odds(session, pA, pB))

    rankings = parse_player_rankings(data)
    match_vs[4], match_vs[5] = rankings[0], rankings[1]

    favorite = who_is_favorite(data)

    # Phase 1: Motivation & surface performance (fills indice_tab[0:4]), plus recent match histories
    await asyncio.gather(
        indice_confiance(session, admin_url, pA_id, match_id, surface, 0, "Motivation", indice_tab=indice_tab),
        indice_confiance(session, admin_url, pB_id, match_id, surface, 1, "Motivation", indice_tab=indice_tab),
        last_matchs(session, today, match_vs, admin_url, pA_id, match_id, 0, favorite),
        last_matchs(session, today, match_vs, admin_url, pB_id, match_id, 1, favorite)
    )

    # Phase 2: Head-to-Head table (safely uses indice_tab[1] and indice_tab[3] computed in Phase 1)
    await h2h_table(data, match_vs, session, MatchContext(surface, admin_url, header, match_id), indice_tab=indice_tab)
            
    compare_players(match_vs)

    match_vs, indice_tab = await odds_match(match_vs, indice_tab, session=session, odds_future=odds_future)

    compare_indice(indice_tab, match_vs)

    elo_A, elo_B = EloMatcher.find_elo_ratings(elo, match_vs[2], match_vs[3], surface)

    if elo_A.replace(".","").isdigit():
        match_vs[40] = elo_A
    if elo_B.replace(".","").isdigit():
        match_vs[41] = elo_B

    alpha_res = evaluate_alpha_strategy(
        match_vs[36], match_vs[37],
        match_vs[38], match_vs[39],
        match_vs[40], match_vs[41],
        match_vs[2], match_vs[3]
    )
    print(f"  {alpha_res['summary']}")

    record_alpha_selection(
        match_vs[0], match_vs[1],
        match_vs[2], match_vs[3],
        alpha_res, match
    )

    await generate_match_xlsx(match_vs)

    return ", ".join(match_vs[:4]) + ", " + ", ".join(match_vs[-8:-2]) + \
           ", " + match_vs[15] + ", " + match_vs[26] + ", " + str(indice_tab[-1]) + \
           ", " + match_vs[19] + ", " + match_vs[30]