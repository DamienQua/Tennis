from bs4 import BeautifulSoup

class SurfacePerformanceAnalyzer:
    def __init__(self, data_fetcher, admin_url):
        self.data_fetcher = data_fetcher
        self.admin_url = admin_url

    async def analyze(self, match_id, surface, flag):
        stats_html = await self.data_fetcher.fetch_data(self.admin_url, {"action": "lazyLoadPanes", "pane": "statistics", "matchID": match_id})
        data = BeautifulSoup(stats_html, "lxml")
        i = 1 if flag == 0 else 4
        
        surface_indices = {"Hard": 12, "Indoor Hard": 19, "Carpet": 26, "Clay": 33, "Grass": 40}
        win_sur = float(data.find_all(class_="table match-preview-statistics-table")[i].find_all("td")[surface_indices[surface]].text.replace("%", "").replace("N/A", "0"))
        
        rank = 10
        for j in range(12, 41, 7):
            if win_sur > float(data.find_all(class_="table match-preview-statistics-table")[i].find_all("td")[j].text.replace("%", "").replace("N/A", "0")):
                rank += 10
        return rank