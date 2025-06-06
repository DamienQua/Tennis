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
from bs4 import BeautifulSoup
import time
import numpy as np
import jaro
from itertools import takewhile
from h2h_table import h2h_table, MatchContext
from last_matchs import last_matchs
from compare_players import compare_players
from odds_match import odds_match
from indice_confiance import indice_confiance
from compare_indice import compare_indice
from generate_match_xlsx import generate_match_xlsx
from variables import indice_tab

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

def determine_tournament_and_surface(match, tournaments):
    same_tour = np.zeros(len(tournaments), float)
    for tourn in tournaments:
        same_tour[np.where(tournaments == tourn)[0][0]] = jaro.jaro_winkler_metric(match.split("2025-")[1].split("/")[0], tourn.split(" (")[0].lower())
    tour, surface = tournaments[same_tour.argmax(0)].split(" (")[0], tournaments[same_tour.argmax(0)].split("- ")[1].split(" Court")[0]
    return tour, surface

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

def get_player_elo(player, match_player_name, surface):
    player_vs = " ".join(takewhile(lambda x: not (x.isdigit() or x.replace(".", "", 1).isdigit()), player.split(" ")))
    if jaro.jaro_winkler_metric(match_player_name, player_vs) >= 0.9:
        return extract_elo_rating(player, player_vs, surface)
    return ""

def find_elo_ratings(elo, match_vs, surface):
    elo_A = next((get_player_elo(player, match_vs[2], surface) for player in elo.split("\n") if get_player_elo(player, match_vs[2], surface)), "")
    elo_B = next((get_player_elo(player, match_vs[3], surface) for player in elo.split("\n") if get_player_elo(player, match_vs[3], surface)), "")
    return elo_A, elo_B

def extract_elo_rating(player, player_name, surface):
    err = 0
    elo = ""
    while not elo.replace(".","").isdigit():
        if "Hard" in surface:
            elo = player.replace("-", " ").split(" ")[player_name.replace("-", " ").count(" ")+1+err]
        elif surface == "Clay":
            elo = player.replace("-", " ").split(" ")[player_name.replace("-", " ").count(" ")+2+err]
        else:
            elo = player.replace("-", " ").split(" ")[player_name.replace("-", " ").count(" ")+3+err]
        err += 1
    return elo

async def analyze_match(session, header, match, tournaments, elo):
    global indice_tab
    today = time.time()
    match_vs = np.chararray(44, itemsize=100, unicode=True)
    admin_url = "https://tennisinsight.com/wp-admin/admin-ajax.php"

    abc = await fetch_data(session, match)
    pA_id, pB_id = extract_player_ids(abc)
    match_id = match.split("match/")[1].split("/")[0]

    overview_data = await fetch_data(session, admin_url, 'post', {"action": "lazyLoadPanes", "pane": "overview", "matchID": match_id})
    data = BeautifulSoup(overview_data, "lxml")

    tour, surface = determine_tournament_and_surface(match, tournaments)
    match_vs[0] = tour
    match_vs[1] = surface

    for i in range(1, 3):
        match_vs[i+1] = data.text.split("for ")[i].split("\n")[0].replace("-Vinolas","").replace(" Vitus Nodskov", "")

    rankings = parse_player_rankings(data)
    match_vs[4], match_vs[5] = rankings[0], rankings[1]

    favorite = who_is_favorite(data)

    tasks = [
        indice_confiance(session, admin_url, pA_id, match_id, surface, 0, "Motivation"),
        indice_confiance(session, admin_url, pB_id, match_id, surface, 1, "Motivation"),
        h2h_table(data, match_vs, session, MatchContext(surface, admin_url, header, match_id)),
        last_matchs(session, today, match_vs, admin_url, pA_id, match_id, 0, favorite),
        last_matchs(session, today, match_vs, admin_url, pB_id, match_id, 1, favorite)
    ]

    await asyncio.gather(*tasks)
            
    compare_players(match_vs)

    match_vs, indice_tab = await odds_match(match_vs, indice_tab)

    compare_indice(indice_tab, match_vs)

    elo_A, elo_B = find_elo_ratings(elo, match_vs, surface)

    if elo_A.replace(".","").isdigit():
        match_vs[40] = elo_A
    if elo_B.replace(".","").isdigit():
        match_vs[41] = elo_B

    await generate_match_xlsx(match_vs)

    return ", ".join(match_vs[:4]) + ", " + ", ".join(match_vs[-8:-2]) + \
           ", " + match_vs[15] + ", " + match_vs[26] + ", " + str(indice_tab[-1])