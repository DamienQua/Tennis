from bs4 import BeautifulSoup
from datetime import date
from variables import indice_tab
from surface_performance_analyzer import SurfacePerformanceAnalyzer
from match_statistics_analyzer import MatchStatisticsAnalyzer

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
        def get_year_index(show_class, year):
            for i, item in enumerate(show_class):
                if str(year) in item.text:
                    return i + 1
            return -1

        def count_matches_in_year(show_class, start_index):
            count = 0
            for i in range(start_index, len(show_class)):
                if show_class[i].text == "Date":
                    break
                count += 1
            return count
        show_class = data.find(id="activity-table").find_all(class_="show")
        year = date.today().year
        try:
            start_index = get_year_index(show_class, year)
            if start_index == -1:
                return -1
            return count_matches_in_year(show_class, start_index)
        except:
            return -1

    def calculate_motivation_index(self, cat, nb_matchs, flag):
        index = 2 * flag
        thresholds = {
            "250": (0, 2),
            "500": (0, 2),
            "1000": (0, float('inf')),
            "Slam": (0, float('inf'))
        }
        for key, (low, high) in thresholds.items():
            if key in cat:
                if nb_matchs < 0:
                    indice_tab[index] = 0
                elif low <= nb_matchs < high:
                    indice_tab[index] = 50
                else:
                    indice_tab[index] = 100
                break

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
        self.stats_analyzer = MatchStatisticsAnalyzer() 

    async def analyze(self, match_url, flag):
        match_id = self.extract_match_id(match_url)
        stats_match = await self.fetch_match_stats(match_id)
        serve_return_stats = self.stats_analyzer.calculate_serve_return_stats(stats_match, flag)
        tiebreak_stats = self.stats_analyzer.calculate_tiebreak_stats(stats_match, flag)
        indice_tab[6:18] = serve_return_stats
        indice_tab[18:20] = tiebreak_stats

    def extract_match_id(self, match_url):
        return match_url.split("match/")[1].split("/")[0]

    async def fetch_match_stats(self, match_id):
        stats_match_html = await self.data_fetcher.fetch_data(self.admin_url, {"action": "showMatchStats", "matchID": match_id, "refresh": "true"})
        return BeautifulSoup(stats_match_html, "lxml")

async def indice_confiance(session, admin_url, player_id, match_id, surface, flag, choix, match_url=""):
    global indice_tab
    data_fetcher = TennisDataFetcher(session)

    if choix == "Motivation":
        motivation_analyzer = MotivationAnalyzer(data_fetcher, admin_url)
        await motivation_analyzer.analyze(player_id, match_id, surface, flag)
    
    elif choix == "Tactique":
        tactics_analyzer = TacticsAnalyzer(data_fetcher, admin_url)
        await tactics_analyzer.analyze(match_url, flag)
    
    elif choix == "Surface":
        surface_analyzer = SurfacePerformanceAnalyzer(data_fetcher, admin_url)
        indice_tab[2*flag+1] = await surface_analyzer.analyze(match_id, surface, flag)