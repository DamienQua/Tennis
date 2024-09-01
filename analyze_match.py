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
from variables import indice_tab

async def fetch_data(session, url, method='get', data=None):
    if method == 'get':
        async with session.get(url) as response:
            return await response.text()
    elif method == 'post':
        async with session.post(url, data=data) as response:
            return await response.text()

async def analyze_match(session, header, match, tournaments, elo):
    global indice_tab
    today = time.time()
    match_vs = np.chararray(42, itemsize=100, unicode=True)
    admin_url = "https://tennisinsight.com/wp-admin/admin-ajax.php"

    abc = await fetch_data(session, match)
    pA_id = abc.split("?playerid=")[1].split('"')[0]
    pB_id = abc.split("?playerid=")[2].split('"')[0]
    match_id = match.split("match/")[1].split("/")[0]

    overview_data = await fetch_data(session, admin_url, 'post', {"action": "lazyLoadPanes", "pane": "overview", "matchID": match_id})
    data = BeautifulSoup(overview_data, "lxml")

    same_tour = np.zeros(len(tournaments), float)
    for tourn in tournaments:
        same_tour[np.where(tournaments == tourn)[0][0]] = jaro.jaro_winkler_metric(match.split("2024-")[1].split("/")[0], tourn.split(" (")[0].lower())
    tour, surface = tournaments[same_tour.argmax(0)].split(" (")[0], tournaments[same_tour.argmax(0)].split("- ")[1].split(" Court")[0]
    match_vs[0] = tour
    match_vs[1] = surface

    tasks = [
        indice_confiance(session, admin_url, pA_id, match_id, surface, 0, "Motivation"),
        indice_confiance(session, admin_url, pB_id, match_id, surface, 1, "Motivation"),
        h2h_table(data, match_vs, session, MatchContext(surface, admin_url, header, match_id)),
        last_matchs(session, today, match_vs, admin_url, pA_id, match_id, 0),
        last_matchs(session, today, match_vs, admin_url, pB_id, match_id, 1)
    ]

    await asyncio.gather(*tasks)

    for i in range(1, 3):
        match_vs[i+1] = data.text.split("for ")[i].split("\n")[0].replace("-Vinolas","").replace(" Vitus Nodskov", "")

    for i in range(2):
        try:
            match_vs[i+4] = int(data.text.replace("Unknown","1000").split("(HI")[i].split("\n")[-1].strip())
        except:
            match_vs[i+4] = 1000
            
    compare_players(match_vs)

    match_vs, indice_tab = await odds_match(match_vs, indice_tab)

    compare_indice(indice_tab, match_vs)

    elo_A, elo_B = "", ""
    err = 0
    for player in elo.split("\n"):
        player_vs = " ".join(takewhile(lambda x: not (x.isdigit() or x.replace(".", "", 1).isdigit()), player.split(" ")))
        if jaro.jaro_winkler_metric(match_vs[2], player_vs) >= 0.85 and elo_A == "":
            while not elo_A.replace(".","").isdigit(): 
                if "Hard" in surface:
                    elo_A = player.replace("-", " ").split(" ")[match_vs[2].replace("-", " ").count(" ")+1+err]
                elif surface == "Clay":
                    elo_A = player.replace("-", " ").split(" ")[match_vs[2].replace("-", " ").count(" ")+2+err]
                else:
                    elo_A = player.replace("-", " ").split(" ")[match_vs[2].replace("-", " ").count(" ")+3+err]
                err += 1
        if jaro.jaro_winkler_metric(match_vs[3], player_vs) >= 0.85 and elo_B == "":
            while not elo_B.replace(".","").isdigit():
                if "Hard" in surface:
                    elo_B = player.replace("-", " ").split(" ")[match_vs[3].replace("-", " ").count(" ")+1+err]
                elif surface == "Clay":
                    elo_B = player.replace("-", " ").split(" ")[match_vs[3].replace("-", " ").count(" ")+2+err]
                else:
                    elo_B = player.replace("-", " ").split(" ")[match_vs[3].replace("-", " ").count(" ")+3+err]
                err += 1
        err = 0
        if elo_A != "" and elo_B != "":
            break

    if elo_A.replace(".","").isdigit():
        match_vs[40] = elo_A
    if elo_B.replace(".","").isdigit():
        match_vs[41] = elo_B

    return ", ".join(match_vs[:4]) + ", " + ", ".join(match_vs[-6:]) + \
           ", " + match_vs[15] + ", " + match_vs[26] + ", " + str(indice_tab[-1])