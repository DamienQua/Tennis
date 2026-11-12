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
import time

from bs4 import BeautifulSoup
import jaro
import numpy as np

from analysis.compare_indice import compare_indice
from analysis.compare_players import compare_players
from analysis.h2h_table import h2h_table, MatchContext
from analysis.indice_confiance import indice_confiance
from analysis.last_matchs import last_matchs
from data_providers.elo_matcher import EloMatcher
from data_providers.odds_match import odds_match, fetch_both_odds
from strategy.alpha_strategy import evaluate_alpha_strategy
from strategy.alpha_tracker import record_alpha_selection
from strategy.generate_match_xlsx import generate_match_xlsx

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
    """Executes HTTP request to retrieve match preview or admin data."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            result = await _attempt_fetch(session, url, method, data)
            if result is not None:
                return result
            if attempt < max_retries - 1:
                await asyncio.sleep(1.0 * (attempt + 1))
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            if attempt < max_retries - 1:
                await asyncio.sleep(1.0 * (attempt + 1))
    return ""

def _ids_from_soup(soup_abc):
    if not soup_abc:
        return []
    seen = []
    for link_elem in soup_abc.find_all('a'):
        href = link_elem.get('href', '')
        if '/player/?playerid=' in href:
            match_obj = re.search(r'playerid=(\d+)', href)
            valid_link = (
                match_obj
                and match_obj.group(1) not in seen
                and 'General Comments' not in link_elem.text
            )
            if valid_link:
                seen.append(match_obj.group(1))
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
    """Extracts unique player IDs for player A and player B."""
    ids = _ids_from_soup(soup_abc)
    if len(ids) < 2 and isinstance(abc, str):
        ids = _ids_from_regex(abc)
    player_a_id = ids[0] if len(ids) > 0 else ""
    player_b_id = ids[1] if len(ids) > 1 else ""
    return player_a_id, player_b_id

def clean_player_name(name):
    """Cleans player name string by removing unwanted suffixes."""
    cleaned = re.sub(r'^\s*[\(\[][A-Za-z0-9/]+[\)\]]\s*', '', name.strip())
    cleaned = cleaned.replace("-Vinolas", "").replace(" Vitus Nodskov", "").strip()
    if cleaned == "Cori Gauff":
        return "Coco Gauff"
    return cleaned

def _names_from_title(soup_abc):
    titles = soup_abc.find_all(class_="profile-title")
    if len(titles) >= 2:
        player_a = clean_player_name(titles[0].text)
        player_b = clean_player_name(titles[1].text)
        if player_a and player_b:
            return player_a, player_b
    return None

def _names_from_links(soup_abc):
    players = []
    seen_ids = set()
    for link_elem in soup_abc.find_all('a'):
        href = link_elem.get('href', '')
        if '/player/?playerid=' in href:
            pid = href.split('playerid=')[-1]
            text = link_elem.text.strip()
            if pid not in seen_ids and text and 'General Comments' not in text:
                seen_ids.add(pid)
                players.append(clean_player_name(text))
    return (players[0], players[1]) if len(players) >= 2 else None

def _names_from_overview(data_text):
    for_parts = data_text.split("for ")
    if len(for_parts) >= 3:
        player_a = clean_player_name(for_parts[1].split("\n")[0])
        player_b = clean_player_name(for_parts[2].split("\n")[0])
        if player_a and player_b:
            return player_a, player_b
    return None

def _names_from_slug(match_url):
    parts = [part for part in match_url.split('/') if part]
    match_slug = parts[-1] if parts else ""
    if '-vs-' in match_slug:
        slug_parts = match_slug.split('-vs-')
        if len(slug_parts) >= 2:
            return slug_parts[0].replace('-', ' ').title(), slug_parts[1].replace('-', ' ').title()
    return None

def extract_player_names(soup_abc, match_url, data_text=""):
    """Extracts player names from title, links, overview, or URL slug."""
    return (
        _names_from_title(soup_abc)
        or _names_from_links(soup_abc)
        or _names_from_overview(data_text)
        or _names_from_slug(match_url)
        or ("Player A", "Player B")
    )

def extract_tournament_slug(match_url):
    """Extracts tournament slug identifier from match URL."""
    found = re.search(r'/\d{4}-([^/]+)/', match_url)
    if found:
        return found.group(1)
    parts = [part for part in match_url.split("/") if part]
    return parts[-2] if len(parts) >= 2 else match_url

def determine_tournament_and_surface(match, tournaments):
    """Determines tournament name and court surface from URL and metadata."""
    slug = extract_tournament_slug(match)
    if tournaments is not None and len(tournaments) > 0:
        t_list = list(tournaments)
        same_tour = np.zeros(len(t_list), float)
        for idx, tourn in enumerate(t_list):
            same_tour[idx] = jaro.jaro_winkler_metric(slug, tourn.split(" (")[0].lower())
        best_idx = int(same_tour.argmax(0))
        tour_str = t_list[best_idx]
        tour = tour_str.split(" (")[0]
        surface = tour_str.split("- ")[1].split(" Court")[0] if "- " in tour_str else "Clay"
        return tour, surface
    clean_tour = slug.replace("-", " ").title()
    return clean_tour, "Clay"

def parse_player_rankings(data):
    """Parses player ATP/WTA rankings from overview HTML."""
    rankings = []
    for idx in range(2):
        try:
            clean_txt = data.text.replace("Unknown", "1000")
            ranking = int(clean_txt.split("(HI")[idx].split("\n")[-1].strip())
        except (ValueError, IndexError, AttributeError):
            ranking = 1000
        rankings.append(ranking)
    return rankings

def who_is_favorite(data):
    """Identifies favorite player based on odds."""
    try:
        left_val = float(data.find(class_="mp_bio_left").find_all("li")[-1].text.strip())
        right_val = float(data.find(class_="mp_bio_right").find_all("li")[-1].text.strip())
        return [1, 0] if left_val > right_val else [0, 1]
    except (ValueError, IndexError, AttributeError):
        return [0, 0]

async def _fetch_match_soups(session, match, admin_url):
    """Fetches and parses main page and overview AJAX pane for a match."""
    if not match or "match/" not in match:
        print(f"⚠️ URL de match invalide : {match}")
        return None
    parts = match.split("match/")[1].split("/")
    match_id = parts[0] if parts else ""
    if not match_id:
        return None
    overview_req = {"action": "lazyLoadPanes", "pane": "overview", "matchID": match_id}
    abc, overview_data = await asyncio.gather(
        fetch_data(session, match),
        fetch_data(session, admin_url, 'post', overview_req)
    )
    soup_abc = BeautifulSoup(abc, "lxml")
    data = BeautifulSoup(overview_data, "lxml")
    p_a_id, p_b_id = extract_player_ids(abc, soup_abc)
    if not p_a_id or not p_b_id:
        print(f"⚠️ Identifiants joueurs introuvables pour {match} - match ignoré.")
        return None
    return {
        "match_id": match_id,
        "soup_abc": soup_abc,
        "data": data,
        "ids": (p_a_id, p_b_id)
    }

def _populate_initial_metadata(
        match_vs,
        match,
        tournaments,
        soup_abc,
        data
) -> str:
    """Populates tournament, surface, players, and rankings into match vector."""
    tour, surface = determine_tournament_and_surface(match, tournaments)
    match_vs[0], match_vs[1] = tour, surface
    p_a, p_b = extract_player_names(soup_abc, match, data.text)
    match_vs[2], match_vs[3] = p_a, p_b
    rankings = parse_player_rankings(data)
    match_vs[4], match_vs[5] = rankings[0], rankings[1]
    return surface

async def _execute_analysis_phases(
        session,
        admin_url,
        header,
        parsed,
        surface,
        match_vs,
        indice_tab
):
    """Executes motivation, recent matches, and H2H analysis phases."""
    today = time.time()
    favorite = who_is_favorite(parsed["data"])
    ids = parsed["ids"]
    m_id = parsed["match_id"]
    await asyncio.gather(
        indice_confiance(
            session, admin_url, ids[0], m_id, surface, 0, "Motivation",
            indice_tab=indice_tab
        ),
        indice_confiance(
            session, admin_url, ids[1], m_id, surface, 1, "Motivation",
            indice_tab=indice_tab
        ),
        last_matchs(session, today, match_vs, admin_url, ids[0], m_id, 0, favorite),
        last_matchs(session, today, match_vs, admin_url, ids[1], m_id, 1, favorite)
    )
    ctx = MatchContext(surface, admin_url, header, m_id)
    await h2h_table(parsed["data"], match_vs, session, ctx, indice_tab=indice_tab)

def _evaluate_and_record_strategy(
        elo: str,
        match_vs: np.ndarray,
        surface: str,
        match: str
) -> None:
    """Computes Elo ratings, evaluates Alpha strategy, and records selection."""
    elo_a, elo_b = EloMatcher.find_elo_ratings(elo, match_vs[2], match_vs[3], surface)
    if elo_a.replace(".", "").isdigit():
        match_vs[40] = elo_a
    if elo_b.replace(".", "").isdigit():
        match_vs[41] = elo_b
    alpha_res = evaluate_alpha_strategy(
        match_vs[36], match_vs[37], match_vs[38], match_vs[39],
        match_vs[40], match_vs[41], match_vs[2], match_vs[3]
    )
    print(f"  {alpha_res['summary']}")
    record_alpha_selection(
        match_vs[0], match_vs[1], match_vs[2], match_vs[3], alpha_res, match
    )

def _format_match_summary(match_vs: np.ndarray, indice_tab: np.ndarray) -> str:
    """Formats the match vector and confidence index into final summary string."""
    return (
        ", ".join(match_vs[:4]) + ", " + ", ".join(match_vs[-8:-2]) +
        ", " + match_vs[15] + ", " + match_vs[26] + ", " + str(indice_tab[-1]) +
        ", " + match_vs[19] + ", " + match_vs[30]
    )

async def analyze_match(session, header, match, tournaments, elo):
    """Main entry point orchestrating full match preview and analysis."""
    admin_url = "https://tennisinsight.com/wp-admin/admin-ajax.php"
    parsed = await _fetch_match_soups(session, match, admin_url)
    if not parsed:
        return ""

    match_vs = np.full(44, "", dtype="<U100")
    indice_tab = np.zeros(25)

    surface = _populate_initial_metadata(
        match_vs, match, tournaments, parsed["soup_abc"], parsed["data"]
    )
    odds_future = asyncio.create_task(fetch_both_odds(session, match_vs[2], match_vs[3]))

    await _execute_analysis_phases(
        session, admin_url, header, parsed, surface, match_vs, indice_tab
    )
    compare_players(match_vs)
    match_vs, indice_tab = await odds_match(
        match_vs, indice_tab, session=session, odds_future=odds_future
    )
    compare_indice(indice_tab, match_vs)

    _evaluate_and_record_strategy(elo, match_vs, surface, match)
    await generate_match_xlsx(match_vs)

    return _format_match_summary(match_vs, indice_tab)
