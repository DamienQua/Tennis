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
from h2h_table import h2h_table, MatchContext
from last_matchs import last_matchs
from compare_players import compare_players
from odds_match import odds_match, fetch_both_odds
from indice_confiance import indice_confiance
from compare_indice import compare_indice
from generate_match_xlsx import generate_match_xlsx
from elo_matcher import EloMatcher

async def fetch_data(session, url, method='get', data=None):
    if method == 'get':
        async with session.get(url) as response:
            return await response.text()
    elif method == 'post':
        async with session.post(url, data=data) as response:
            return await response.text()

def extract_player_ids(abc):
    pA_id = abc.split("?playerid=")[1].split('"')[0]
    pB_id = abc.split("?playerid=")[2].split('"')[0]
    return pA_id, pB_id

def clean_player_name(name):
    cleaned = re.sub(r'^\s*[\(\[][A-Za-z0-9/]+[\)\]]\s*', '', name.strip())
    cleaned = cleaned.replace("-Vinolas", "").replace(" Vitus Nodskov", "").strip()
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
    pA_id, pB_id = extract_player_ids(abc)

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

    await generate_match_xlsx(match_vs)

    return ", ".join(match_vs[:4]) + ", " + ", ".join(match_vs[-8:-2]) + \
           ", " + match_vs[15] + ", " + match_vs[26] + ", " + str(indice_tab[-1])