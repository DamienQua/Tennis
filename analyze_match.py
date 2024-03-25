import numpy as np
import time
import jaro
from itertools import takewhile
from bs4 import BeautifulSoup
from h2h_table import h2h_table
from last_matchs import last_matchs
from compare_players import compare_players
from odds_match import odds_match
from indice_confiance import indice_confiance
from compare_indice import compare_indice

def analyze_match(cpt, session, header, match, tournaments, elo) :
    today = time.time()
    match_vs = np.chararray(42, itemsize = 100, unicode = True)
    indice_tab = np.zeros(25)
    admin_url = "https://tennisinsight.com/wp-admin/admin-ajax.php"
    abc = session.get(match, headers = header).text
    pA_id = abc.split("?playerid=")[1].split('"')[0]
    pB_id = abc.split("?playerid=")[2].split('"')[0]
    match_id = match.split("match/")[1].split("/")[0]
    data = BeautifulSoup(session.post(admin_url, {"action" : "lazyLoadPanes", "pane" : "overview", "matchID" : match_id}, headers = header).content, "lxml")
    
    # Tour and Surface
    same_tour = np.zeros(len(tournaments), float)
    for tourn in tournaments :
        same_tour[np.where(tournaments == tourn)[0][0]] = jaro.jaro_winkler_metric(match.split("2024-")[1].split("/")[0], tourn.split(" (")[0].lower())
    tour, surface = tournaments[same_tour.argmax(0)].split(" (")[0], tournaments[same_tour.argmax(0)].split("- ")[1].split(" Court")[0]
    #print(tour, surface)
    match_vs[0] = tour
    match_vs[1] = surface

    indice_confiance(indice_tab, session, admin_url, header, pA_id, match_id, surface, 0, "Motivation")
    indice_confiance(indice_tab, session, admin_url, header, pB_id, match_id, surface, 1, "Motivation")

    # Player A vs Player B
    for i in range(1, 3) :
        match_vs[i+1] = data.text.split("for ")[i].split("\n")[0].replace("-Vinolas","").replace(" Vitus Nodskov", "")

    # Rank A vs Rank B
    for i in range(2) :
        try :
            match_vs[i+4] = int(data.text.replace("Unknown","1000").split("(HI")[i].split("\n")[-1].strip())
        except:
            match_vs[i+4] = 1000
    
    # H2H 
    h2h_table(data, match_vs, surface, indice_tab, session, admin_url, header, match_id)

    # Stats
    # Player A
    last_matchs(session, today, match_vs, admin_url, header, pA_id, match_id, 0)
    # Player B
    last_matchs(session, today, match_vs, admin_url, header, pB_id, match_id, 1)

    compare_players(match_vs)

    # Odds Match
    odds_match(match_vs, indice_tab)

    compare_indice(indice_tab, match_vs)

    # ELOs
    elo_A, elo_B = "", ""
    err = 0
    for player in elo.split("\n") :
        player_vs = " ".join(takewhile(lambda x: not (x.isdigit() or x.replace(".", "", 1).isdigit()), player.split(" ")))
        if jaro.jaro_winkler_metric(match_vs[2], player_vs) >= 0.80 and elo_A == "" :
            while not elo_A.replace(".","").isdigit() : 
                if "Hard" in surface :
                    elo_A = player.replace("-", " ").split(" ")[match_vs[2].replace("-", " ").count(" ")+1+err]
                elif surface == "Clay" :
                    elo_A = player.replace("-", " ").split(" ")[match_vs[2].replace("-", " ").count(" ")+2+err]
                else :
                    elo_A = player.replace("-", " ").split(" ")[match_vs[2].replace("-", " ").count(" ")+3+err]
                err += 1
        if jaro.jaro_winkler_metric(match_vs[3], player_vs) >= 0.80 and elo_B == "" :
            while not elo_B.replace(".","").isdigit() :
                if "Hard" in surface :
                    elo_B = player.replace("-", " ").split(" ")[match_vs[3].replace("-", " ").count(" ")+1+err]
                elif surface == "Clay" :
                    elo_B = player.replace("-", " ").split(" ")[match_vs[3].replace("-", " ").count(" ")+2+err]
                else :
                    elo_B = player.replace("-", " ").split(" ")[match_vs[3].replace("-", " ").count(" ")+3+err]
                err += 1
        err = 0
        if elo_A != "" and elo_B != "" :
            break

    if elo_A.replace(".","").isdigit() :
        match_vs[40] = elo_A
    if elo_B.replace(".","").isdigit() :
        match_vs[41] = elo_B

    return ", ".join(match_vs[:4]) + ", " + ", ".join(match_vs[-6:]) + \
           ", " + match_vs[15] + ", " + match_vs[26] + ", " + str(indice_tab[-1])