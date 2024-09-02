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
        data_html = await self.fetch_player_activity(player_id, match_id)
        data = BeautifulSoup(data_html, "lxml")
        
        cat = self.get_tournament_category(data)
        nb_matchs = self.count_matches(data)
        
        self.calculate_motivation_index(cat, nb_matchs, flag)
        
        await self.analyze_surface_performance(match_id, surface, flag)        

    async def fetch_player_activity(self, player_id, match_id):
        pAB_param = {"action": "playerActivity", "activityOffset": "0", "basic-activity-option": "3", "odds": "0", "filterType": "basic", "playerID": player_id, "matchID": match_id}
        return await self.data_fetcher.fetch_data(self.admin_url, pAB_param)

    def get_tournament_category(self, data):
        try:
            return data.find(id="activity-table").find_all(class_="subheader")[0].text
        except IndexError:
            return "250"

    def count_matches(self, data):
        show_class = data.find(id="activity-table").find_all(class_="show")
        year = date.today().year
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
        return nb_matchs

    def calculate_motivation_index(self, cat, nb_matchs, flag):
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

    async def analyze_surface_performance(self, match_id, surface, flag):
        stats_html = await self.data_fetcher.fetch_data(self.admin_url, {"action": "lazyLoadPanes", "pane": "statistics", "matchID": match_id})
        data = BeautifulSoup(stats_html, "lxml")
        i = 1 if flag == 0 else 4
        
        surface_indices = {"Hard": 12, "Indoor Hard": 19, "Carpet": 26, "Clay": 33, "Grass": 40}
        win_sur = float(data.find_all(class_="table match-preview-statistics-table")[i].find_all("td")[surface_indices[surface]].text.replace("%","").replace("N/A","0"))
        
        rank = 10
        for j in range(12, 41, 7):
            if win_sur > float(data.find_all(class_="table match-preview-statistics-table")[i].find_all("td")[j].text.replace("%","").replace("N/A","0")):
                rank += 10
        indice_tab[2*flag+1] = rank

class TacticsAnalyzer:
    def __init__(self, data_fetcher, admin_url):
        self.data_fetcher = data_fetcher
        self.admin_url = admin_url

    async def analyze(self, match_url, flag):
        match_id = self.extract_match_id(match_url)
        stats_match = await self.fetch_match_stats(match_id)
        
        self.calculate_serve_return_stats(stats_match, flag)
        self.calculate_tiebreak_stats(stats_match, flag)

    def extract_match_id(self, match_url):
        return match_url.split("match/")[1].split("/")[0]

    async def fetch_match_stats(self, match_id):
        stats_match_html = await self.data_fetcher.fetch_data(self.admin_url, {"action": "showMatchStats", "matchID": match_id, "refresh": "true"})
        return BeautifulSoup(stats_match_html, "lxml")

    def calculate_serve_return_stats(self, stats_match, flag):
        j2 = 2 if flag == 1 else 0
        points_first_serve = float(stats_match.find_all(class_="col-xs-4")[12+j2].text.strip().split("%")[0])
        points_second_serve = float(stats_match.find_all(class_="col-xs-4")[15+j2].text.strip().split("%")[0])
        return_first_serve = float(stats_match.find_all(class_="col-xs-4")[24+j2].text.strip().split("%")[0])
        return_second_serve = float(stats_match.find_all(class_="col-xs-4")[27+j2].text.strip().split("%")[0])
        points_save_bp = float(stats_match.find_all(class_="col-xs-4")[18+j2].text.strip().split("%")[0])
        return_save_bp = float(stats_match.find_all(class_="col-xs-4")[30+j2].text.strip().split("%")[0])
        
        if flag == 0:
            indice_tab[6:18] = [points_first_serve, 100-points_first_serve, points_second_serve, 100-points_second_serve,
                                return_first_serve, 100-return_first_serve, return_second_serve, 100-return_second_serve,
                                points_save_bp, 100-points_save_bp, return_save_bp, 100-return_save_bp]
        else:
            indice_tab[6:18] = [100-points_first_serve, points_first_serve, 100-points_second_serve, points_second_serve,
                                100-return_first_serve, return_first_serve, 100-return_second_serve, return_second_serve,
                                100-points_save_bp, points_save_bp, 100-return_save_bp, return_save_bp]

    def calculate_tiebreak_stats(self, stats_match, flag):
        scores = re.sub(r"\([^)]*\)", "", stats_match.find_all(class_="col-xs-12")[0].find_all("h4")[0].text.strip())
        tie_break_j1, tie_break_j2 = 0, 0
        if scores != "":
            tie_break_j1 = sum(int(s[0]) >= 6 and int(s[1]) >= 6 and int(s[0]) > int(s[1]) for score in scores.split(" ") for s in (score.split("-"),))
            tie_break_j2 = sum(int(s[0]) >= 6 and int(s[1]) >= 6 and int(s[0]) < int(s[1]) for score in scores.split(" ") for s in (score.split("-"),))
        
        if tie_break_j1 + tie_break_j2 != 0:
            indice_tab[18] = 100*tie_break_j1/(tie_break_j1+tie_break_j2)
            indice_tab[19] = 100*tie_break_j2/(tie_break_j1+tie_break_j2)

async def indice_confiance(session, admin_url, player_id, match_id, surface, flag, choix, match_url=""):
    global indice_tab
    data_fetcher = TennisDataFetcher(session)

    if choix == "Motivation":
        motivation_analyzer = MotivationAnalyzer(data_fetcher, admin_url)
        await motivation_analyzer.analyze(player_id, match_id, surface, flag)
    
    elif choix == "Tactique":
        tactics_analyzer = TacticsAnalyzer(data_fetcher, admin_url)
        await tactics_analyzer.analyze(match_url, flag)