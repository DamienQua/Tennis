"""
    Analyzes surface performance statistics for a tennis match.
    
    This class fetches and processes match statistics to calculate a player's performance 
    rank based on their win percentage on a specific surface type.
    
    Args:
        data_fetcher: An object responsible for fetching match data.
        admin_url: The URL for accessing match statistics.
    
    Methods:
        analyze(match_id, surface, flag): Calculates a performance rank based on surface-specific win percentages.
"""

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