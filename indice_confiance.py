from operator import length_hint
from bs4 import BeautifulSoup
from datetime import date
import re

def indice_confiance(indice_tab, session, admin_url, header, player_id, match_id, surface, flag, choix, match_url="") :
    if choix == "Motivation" :
        pAB_param = {"action" : "playerActivity",  "activityOffset": "0", "basic-activity-option": "3", "odds" : "0", "filterType" : "basic", "playerID" : player_id, "matchID" : match_id}
        data = BeautifulSoup(session.post(admin_url, pAB_param, headers = header).content, "lxml")
        show_class = data.find(id="activity-table").find_all(class_="show")
        year = date.today().year
        try :
            cat = data.find(id="activity-table").find_all(class_="subheader")[0].text
        except IndexError :
            cat = "250"
        date_i, nb_matchs = 1, -1
        try :
            if str(year) in show_class[date_i].text :
                date_i += 1
            if str(year-1) in show_class[date_i].text :
                i = date_i + 1
            while show_class[i].text != "Date" :
                i += 1
            while show_class[i].text != "Date" :
                nb_matchs += 1
        except :
                pass
        if "250" in cat or "500" in cat :
            if nb_matchs < 0 :
                indice_tab[2*flag] = 0
            elif 0 <= nb_matchs < 2 :
                indice_tab[2*flag] = 50
            else : 
                indice_tab[2*flag] = 100
        if "1000" in cat or "Slam" in cat :
            if nb_matchs < 0 :
                indice_tab[2*flag] = 50
            else :
                indice_tab[2*flag] = 100

        """ if (len(indice_tab) == 0 and flag == 0) or (len(indice_tab) == 2 and flag == 1) : ## Chall, Future
            if nb_matchs < 0 :
                indice_tab[2*flag] = 0
            elif 0 <= nb_matchs < 2 :
                indice_tab[2*flag] = 25 """
        
        data = BeautifulSoup(session.post(admin_url, {"action" : "lazyLoadPanes", "pane" : "statistics", "matchID" : match_id}, headers = header).content, "lxml")
        stats_table = data.find_all(class_="table match-preview-statistics-table")
        # 1, 4
        # 12, 19, 26, 33, 40
        i, rank = 4, 10
        if flag == 0 :
            i = 1
        if surface == "Hard" :
            win_sur = float(data.find_all(class_="table match-preview-statistics-table")[i].find_all("td")[12].text.replace("%","").replace("N/A","0"))
        if surface == "Indoor Hard" :
            win_sur = float(data.find_all(class_="table match-preview-statistics-table")[i].find_all("td")[19].text.replace("%","").replace("N/A","0"))
        if surface == "Carpet" :
            win_sur = float(data.find_all(class_="table match-preview-statistics-table")[i].find_all("td")[26].text.replace("%","").replace("N/A","0"))
        if surface == "Clay" :
            win_sur = float(data.find_all(class_="table match-preview-statistics-table")[i].find_all("td")[33].text.replace("%","").replace("N/A","0"))
        if surface == "Grass" :
            win_sur = float(data.find_all(class_="table match-preview-statistics-table")[i].find_all("td")[40].text.replace("%","").replace("N/A","0"))
        for j in range(12, 41, 7) :
            if win_sur > float(data.find_all(class_="table match-preview-statistics-table")[i].find_all("td")[j].text.replace("%","").replace("N/A","0")) :
                rank += 10
        indice_tab[2*flag+1] = rank
        flag = 1
    
    if choix == "Tactique" :
        if match_url != "" :
            data = BeautifulSoup(session.get(match_url, headers = header).content, "lxml")
            match_id = match_url.split("match/")[1].split("/")[0]
            stats_match = BeautifulSoup(session.post(admin_url, {"action" : "showMatchStats", "matchID" : match_id, "refresh" : "true"}, headers = header).content, "lxml")
            j2 = 0
            if flag == 1 :
                j2 = 2
            points_first_serve = float(stats_match.find_all(class_="col-xs-4")[12+j2].text.strip().split("%")[0])
            points_second_serve = float(stats_match.find_all(class_="col-xs-4")[15+j2].text.strip().split("%")[0])
            return_first_serve = float(stats_match.find_all(class_="col-xs-4")[24+j2].text.strip().split("%")[0])
            return_second_serve = float(stats_match.find_all(class_="col-xs-4")[27+j2].text.strip().split("%")[0])
            points_save_bp = float(stats_match.find_all(class_="col-xs-4")[18+j2].text.strip().split("%")[0])
            return_save_bp = float(stats_match.find_all(class_="col-xs-4")[30+j2].text.strip().split("%")[0])
            scores = re.sub(r"\([^)]*\)", "", stats_match.find_all(class_="col-xs-12")[0].find_all("h4")[0].text.strip())
            tie_break_j1, tie_break_j2 = 0, 0
            if scores != "" :
                tie_break_j1 = sum(int(s[0]) >= 6 and int(s[1]) >= 6 and int(s[0]) > int(s[1]) for score in scores.split(" ") for s in (score.split("-"),))
                tie_break_j2 = sum(int(s[0]) >= 6 and int(s[1]) >= 6 and int(s[0]) < int(s[1]) for score in scores.split(" ") for s in (score.split("-"),))
            if flag == 0 :
                indice_tab[6] = points_first_serve
                indice_tab[7] = 100-points_first_serve
                indice_tab[8] = points_second_serve
                indice_tab[9] = 100-points_second_serve
                indice_tab[10] = return_first_serve
                indice_tab[11] = 100-return_first_serve
                indice_tab[12] = return_second_serve
                indice_tab[13] = 100-return_second_serve
                indice_tab[14] = points_save_bp
                indice_tab[15] = 100-points_save_bp
                indice_tab[16] = return_save_bp
                indice_tab[17] = 100-return_save_bp
            else :
                indice_tab[6] = 100-points_first_serve
                indice_tab[7] = points_first_serve
                indice_tab[8] = 100-points_second_serve
                indice_tab[9] = points_second_serve
                indice_tab[10] = 100-return_first_serve
                indice_tab[11] = return_first_serve
                indice_tab[12] = 100-return_second_serve
                indice_tab[13] = return_second_serve
                indice_tab[14] = 100-points_save_bp
                indice_tab[15] = points_save_bp
                indice_tab[16] = 100-return_save_bp
                indice_tab[17] = return_save_bp

            if tie_break_j1 + tie_break_j2 != 0:
                indice_tab[18] = 100*tie_break_j1/(tie_break_j1+tie_break_j2)
                indice_tab[19] = 100*tie_break_j2/(tie_break_j1+tie_break_j2)