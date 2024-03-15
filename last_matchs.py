from bs4 import BeautifulSoup
from datetime import datetime

def last_matchs(session, today, match_vs, admin_url, header, player_id, match_id, last_flag) :
    tour_now = BeautifulSoup(session.post(admin_url, {"action" : "lazyLoadPanes", "pane" : "activity", "matchID" : match_id}, headers = header).content, "lxml").find(id="basic-this-tournament-A")["value"].split("At ")[1]
    pAB_param = {"action" : "playerActivity",  "activityOffset": "0", "basic-activity-option": "1", "odds" : "0", "filterType" : "basic", "playerID" : player_id, "matchID" : match_id}
    data = BeautifulSoup(session.post(admin_url, pAB_param, headers = header).content, "lxml")
    last_10_winAB = float(data.text.split("Matches")[1].replace("N/A","0").strip().replace("\t","").split("\n\n")[1].replace("N/A","0").strip().split("%")[0])
    last_50_winAB = float(data.text.split("Matches")[2].replace("N/A","0").strip().replace("\t","").split("\n\n")[1].replace("N/A","0").strip().split("%")[0])
    last_12m_winAB_all = float(data.text.split("months)")[1].replace("N/A","0").strip().replace("\t","").split("\n\n")[1].replace("N/A","0").strip().split("%")[0])
    winAB_all = float(data.text.split("2000)")[1].replace("N/A","0").strip().replace("\t","").split("\n\n")[1].replace("N/A","0").strip().split("%")[0])
    show_class = data.find(id="activity-table").find_all(class_="show")
    nb_match_last_month = 0
    date_i = 1
    one_month = 2629800
    pAB_matchs = data.find_all(class_="activity-clickthroughs no-link")
    m_i = 0
    min_tour = 0
    per_first_serve, points_first_serve, per_save_bp = 0, 0, 0
    for i in range(2, len(show_class)) :
        if show_class[i].text != "Date" :
            if today - datetime.strptime(show_class[date_i].text, "%b %d %Y").timestamp() <= one_month :
                nb_match_last_month += 1
        else : 
            if m_i + nb_match_last_month != 0 :
                date_i += m_i + nb_match_last_month + 1
            else :
                date_i = i+1
            if show_class[date_i].text == "Date" :
                date_i += 1
            d = None 
            while d is None :
                try :
                    d = datetime.strptime(show_class[date_i].text, "%b %d %Y").timestamp()
                except ValueError :
                    date_i -= 1
            if today - datetime.strptime(show_class[date_i].text, "%b %d %Y").timestamp() > one_month :
                break
        if tour_now in data.find(id="activity-table").find("a").text :
            stats_match = BeautifulSoup(session.post(admin_url, {"action" : pAB_matchs[m_i].find_all("a")[1]["data-action"], "matchID" : pAB_matchs[m_i].find_all("a")[1]["data-matchid"]}, headers = header).content, "lxml")
            m_i += 1
            try :
                min_tour += int(stats_match.find("h5").text.split(" m")[0])
                if m_i == 1 and "Qualifying" not in stats_match.text :
                    per_first_serve = float(stats_match.find_all(class_="col-xs-4")[9].text.replace("N/A","0").strip().split("%")[0])
                    points_first_serve = float(stats_match.find_all(class_="col-xs-4")[12].text.replace("N/A","0").strip().split("%")[0])
                    per_save_bp = float(stats_match.find_all(class_="col-xs-4")[18].text.replace("N/A","0").strip().split("%")[0])
            except :
                pass

    pAB_param = {"action" : "playerActivity",  "activityOffset": "0", "basic-activity-option": "2", "odds" : "0", "filterType" : "basic", "playerID" : player_id, "matchID" : match_id}
    data = BeautifulSoup(session.post(admin_url, pAB_param, headers = header).content, "lxml")
    last_12m_winAB_sur = float(data.text.split("months)")[1].replace("N/A","0").strip().replace("\t","").split("\n\n")[1].replace("N/A","0").strip().split("%")[0])
    winAB_sur = float(data.text.split("2000)")[1].replace("N/A","0").strip().replace("\t","").split("\n\n")[1].replace("N/A","0").strip().split("%")[0])
    
    match_vs[14+11*last_flag] = winAB_all
    match_vs[15+11*last_flag] = winAB_sur
    match_vs[16+11*last_flag] = last_12m_winAB_all
    match_vs[17+11*last_flag] = last_12m_winAB_sur
    match_vs[18+11*last_flag] = last_50_winAB
    match_vs[19+11*last_flag] = last_10_winAB
    match_vs[20+11*last_flag] = nb_match_last_month
    match_vs[21+11*last_flag] = min_tour
    match_vs[22+11*last_flag] = per_first_serve
    match_vs[23+11*last_flag] = points_first_serve
    match_vs[24+11*last_flag] = per_save_bp