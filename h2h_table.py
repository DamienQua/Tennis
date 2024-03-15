import time
from datetime import datetime
import re
from numpy import append
from indice_confiance import indice_confiance

def h2h_table(data, match_vs, surface, indice_tab, session, admin_url, header, match_id) :
    h2h_tr = data.find(class_="h2h-matches").find_all("tr")[1:]
    today = time.time()
    year_ms = 365.25*24*3600
    h2h_nb, h2h_y = 0, 0
    winA_all, winB_all = 0, 0
    winA_y, winB_y = 0, 0
    winA_sur, winB_sur = 0, 0
    winA_G, winB_G = 0, 0
    ind, ind_win = 0, 0
    go, flag = "", 0
    if "tied" in data.text :
        ind = 1
    for i in range(2) :
        h2h_nb += int(data.text.strip().split("series ")[1].split(" ")[ind].split("-")[i].split("\n")[0])
    if h2h_nb > 0 :
        for i in range(2) :
            match_vs[i+6] = round(100*int(data.text.strip().split("series ")[1].split(" ")[ind].split("-")[i].split("\n")[0])/h2h_nb, 2)
        for tr in h2h_tr :
            date_ms = datetime.strptime(tr.text.strip().split("\t")[0].strip(), "%b %d %Y").timestamp()
            tour_m, surface_m = tr.text.strip().split("\n")[2], tr.text.strip().split("\n")[5].strip().split(",")[0]
            winner = re.sub("[\(\[].*?[\)\]]", "", tr.text.strip().split("\n")[7].strip()).split(" d")[0].strip()
            try :
                score = re.sub("[\(\[].*?[\)\]]", "", tr.text.strip().split("\n")[9].strip()).replace("ret."," ").replace("w/o", "").strip()
            except :
                score = "0-0 0-0"
            if winner in match_vs[2] :
                ind_win = 0
                if today - date_ms <= year_ms :
                    winA_y += 1
                    winA_all += 1
                    h2h_y += 1 
                if surface in tr.text :
                    winA_sur += 1
                    if go == "" :
                        go = tr.find_all("a")[-1]["href"]
                        flag = 0
                for i in range(len(score.split(" "))) :
                    try :
                        winA_G += int(score.split(" ")[i].split("-")[ind_win])
                        winB_G += int(score.split(" ")[i].split("-")[1-ind_win])
                    except :
                        pass
            else :
                ind_win = 1
                if today - date_ms <= year_ms :
                    winB_y += 1
                    winB_all += 1
                    h2h_y += 1 
                if surface in tr.text :
                    winB_sur += 1
                    if go == "" :
                        go = tr.find_all("a")[-1]["href"]
                        flag = 1
                for i in range(len(score.split(" "))) :
                    try :
                        winA_G += int(score.split(" ")[i].split("-")[ind_win])
                        winB_G += int(score.split(" ")[i].split("-")[1-ind_win])
                    except : 
                        pass
 
        try :
            match_vs[8] = round(100*winA_y/(winA_y + winB_y), 2)
            match_vs[9] = round(100*winB_y/(winA_y + winB_y), 2)
        except :
            for i in range(2) :
                match_vs[i+8] = 0
        try :
            match_vs[10] = round(100*winA_sur/(winA_sur + winB_sur), 2)
            match_vs[11] = round(100*winB_sur/(winA_sur + winB_sur), 2)
        except :
            for i in range(2) :
                match_vs[i+10] = 0
        try :
            match_vs[12] = round(100*winA_G/(winA_G + winB_G), 2)
            match_vs[13] = round(100*winB_G/(winA_G + winB_G), 2)
        except :
            for i in range(2) :
                match_vs[i+12] = 0
        
    else :
        for i in range(8) :
            match_vs[i+6] = 0

    if winA_sur > 0 :
        indice_tab[4] = 2*indice_tab[1]
    if winB_sur > 0 :
        indice_tab[5] = 2*indice_tab[3]

    if go != "" :
        indice_confiance(indice_tab, session, admin_url, header, "", match_id, surface, flag, "Tactique", go)