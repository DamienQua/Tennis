import aiohttp
from bs4 import BeautifulSoup
from datetime import date
import re
from variables import indice_tab

class TennisDataFetcher:
    def __init__(self, session):
        self.session = session

    async def fetch_data(self, url, data=None, method='POST'):
        if method == 'POST':
            async with self.session.post(url, data=data) as response:
                return await response.text()
        else:
            async with self.session.get(url) as response:
                return await response.text()

class MotivationAnalyzer:
    def __init__(self, data_fetcher, admin_url):
        self.data_fetcher = data_fetcher
        self.admin_url = admin_url

    async def analyze(self, player_id, match_id, surface, flag):
        pAB_param = {"action": "playerActivity", "activityOffset": "0", "basic-activity-option": "3", "odds": "0", "filterType": "basic", "playerID": player_id, "matchID": match_id}
        data_html = await self.data_fetcher.fetch_data(self.admin_url, pAB_param)
        data = BeautifulSoup(data_html, "lxml")
        
        show_class = data.find(id="activity-table").find_all(class_="show")
        year = date.today().year
        try:
            cat = data.find(id="activity-table").find_all(class_="subheader")[0].text
        except IndexError:
            cat = "250"
        date_i, nb_matchs = 1, -1
        try:
            if str(year) in show_class[date_i].text:
                date_i += 1
            if str(year-1) in show_class[date_i].text:
                i = date_i + 1
            while show_class[i].text != "Date":
                i += 1
            while show_class[i].text != "Date":
                nb_matchs += 1
        except:
            pass
        
        if "250" in cat or "500" in cat:
            if nb_matchs < 0:
                indice_tab[2*flag] = 0
            elif 0 <= nb_matchs < 2:
                indice_tab[2*flag] = 50
            else: 
                indice_tab[2*flag] = 100
        if "1000" in cat or "Slam" in cat:
            if nb_matchs < 0:
                indice_tab[2*flag] = 50
            else:
                indice_tab[2*flag] = 100

        stats_html = await self.data_fetcher.fetch_data(self.admin_url, {"action": "lazyLoadPanes", "pane": "statistics", "matchID": match_id})
        data = BeautifulSoup(stats_html, "lxml")
        i, rank = 4, 10
        if flag == 0:
            i = 1
        
        surface_indices = {"Hard": 12, "Indoor Hard": 19, "Carpet": 26, "Clay": 33, "Grass": 40}
        win_sur = float(data.find_all(class_="table match-preview-statistics-table")[i].find_all("td")[surface_indices[surface]].text.replace("%","").replace("N/A","0"))
        
        for j in range(12, 41, 7):
            if win_sur > float(data.find_all(class_="table match-preview-statistics-table")[i].find_all("td")[j].text.replace("%","").replace("N/A","0")):
                rank += 10
        indice_tab[2*flag+1] = rank

        return indice_tab

class TacticsAnalyzer:
    def __init__(self, data_fetcher, admin_url):
        self.data_fetcher = data_fetcher
        self.admin_url = admin_url

    async def analyze(self, match_url, flag):
        data_html = await self.data_fetcher.fetch_data(match_url, method='GET')
        data = BeautifulSoup(data_html, "lxml")
        match_id = match_url.split("match/")[1].split("/")[0]
        stats_match_html = await self.data_fetcher.fetch_data(self.admin_url, {"action": "showMatchStats", "matchID": match_id, "refresh": "true"})
        stats_match = BeautifulSoup(stats_match_html, "lxml")
        
        j2 = 2 if flag == 1 else 0
        points_first_serve = float(stats_match.find_all(class_="col-xs-4")[12+j2].text.strip().split("%")[0])
        points_second_serve = float(stats_match.find_all(class_="col-xs-4")[15+j2].text.strip().split("%")[0])
        return_first_serve = float(stats_match.find_all(class_="col-xs-4")[24+j2].text.strip().split("%")[0])
        return_second_serve = float(stats_match.find_all(class_="col-xs-4")[27+j2].text.strip().split("%")[0])
        points_save_bp = float(stats_match.find_all(class_="col-xs-4")[18+j2].text.strip().split("%")[0])
        return_save_bp = float(stats_match.find_all(class_="col-xs-4")[30+j2].text.strip().split("%")[0])
        
        scores = re.sub(r"\([^)]*\)", "", stats_match.find_all(class_="col-xs-12")[0].find_all("h4")[0].text.strip())
        tie_break_j1, tie_break_j2 = 0, 0
        if scores != "":
            tie_break_j1 = sum(int(s[0]) >= 6 and int(s[1]) >= 6 and int(s[0]) > int(s[1]) for score in scores.split(" ") for s in (score.split("-"),))
            tie_break_j2 = sum(int(s[0]) >= 6 and int(s[1]) >= 6 and int(s[0]) < int(s[1]) for score in scores.split(" ") for s in (score.split("-"),))
        
        if flag == 0:
            indice_tab[6:18] = [points_first_serve, 100-points_first_serve, points_second_serve, 100-points_second_serve,
                                return_first_serve, 100-return_first_serve, return_second_serve, 100-return_second_serve,
                                points_save_bp, 100-points_save_bp, return_save_bp, 100-return_save_bp]
        else:
            indice_tab[6:18] = [100-points_first_serve, points_first_serve, 100-points_second_serve, points_second_serve,
                                100-return_first_serve, return_first_serve, 100-return_second_serve, return_second_serve,
                                100-points_save_bp, points_save_bp, 100-return_save_bp, return_save_bp]

        if tie_break_j1 + tie_break_j2 != 0:
            indice_tab[18] = 100*tie_break_j1/(tie_break_j1+tie_break_j2)
            indice_tab[19] = 100*tie_break_j2/(tie_break_j1+tie_break_j2)

        return indice_tab

async def indice_confiance(session, admin_url, player_id, match_id, surface, flag, choix, match_url=""):
    global indice_tab
    data_fetcher = TennisDataFetcher(session)

    if choix == "Motivation":
        motivation_analyzer = MotivationAnalyzer(data_fetcher, admin_url)
        indice_tab = await motivation_analyzer.analyze(player_id, match_id, surface, flag)
    
    elif choix == "Tactique":
        tactics_analyzer = TacticsAnalyzer(data_fetcher, admin_url)
        indice_tab = await tactics_analyzer.analyze(match_url, flag)

    return indice_tab