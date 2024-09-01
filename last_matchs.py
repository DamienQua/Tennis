import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime

class TennisDataFetcher:
    def __init__(self, session, admin_url):
        self.session = session
        self.admin_url = admin_url

    async def fetch_data(self, url, data=None):
        async with self.session.post(url, data=data) as response:
            return await response.text()

    async def fetch_tournament_data(self, match_id):
        tour_now_html = await self.fetch_data(self.admin_url, {"action": "lazyLoadPanes", "pane": "activity", "matchID": match_id})
        return BeautifulSoup(tour_now_html, "lxml").find(id="basic-this-tournament-A")["value"].split("At ")[1]

    async def fetch_player_activity(self, player_id, match_id, activity_option):
        pAB_param = {
            "action": "playerActivity",
            "activityOffset": "0",
            "basic-activity-option": str(activity_option),
            "odds": "0",
            "filterType": "basic",
            "playerID": player_id,
            "matchID": match_id
        }
        data_html = await self.fetch_data(self.admin_url, pAB_param)
        return BeautifulSoup(data_html, "lxml")

    async def fetch_match_statistics(self, pAB_match):
        stats_match_html = await self.fetch_data(self.admin_url, {"action": pAB_match.find_all("a")[1]["data-action"], "matchID": pAB_match.find_all("a")[1]["data-matchid"]})
        return BeautifulSoup(stats_match_html, "lxml")

class TennisDataParser:
    @staticmethod
    def parse_win_percentages(data):
        win_percentages = data.text.split("Matches")[1:3] + data.text.split("months)")[1:2] + data.text.split("2000)")[1:2]
        return [float(percentage.replace("N/A","0").strip().replace("\t","").split("\n\n")[1].replace("N/A","0").strip().split("%")[0]) for percentage in win_percentages]

    @staticmethod
    def parse_match_statistics(stats_match):
        min_tour = int(stats_match.find("h5").text.split(" m")[0])
        per_first_serve = float(stats_match.find_all(class_="col-xs-4")[9].text.replace("N/A","0").strip().split("%")[0])
        points_first_serve = float(stats_match.find_all(class_="col-xs-4")[12].text.replace("N/A","0").strip().split("%")[0])
        per_save_bp = float(stats_match.find_all(class_="col-xs-4")[18].text.replace("N/A","0").strip().split("%")[0])
        return min_tour, per_first_serve, points_first_serve, per_save_bp

class StatisticsProcessor:
    @staticmethod
    def calculate_win_percentages(data):
        return TennisDataParser.parse_win_percentages(data)

    @staticmethod
    async def process_match_statistics(data_fetcher, pAB_matchs, tour_now, m_i):
        stats_match = await data_fetcher.fetch_match_statistics(pAB_matchs[m_i])
        return TennisDataParser.parse_match_statistics(stats_match)

class TennisMatchAnalyzer:
    def __init__(self, session, admin_url):
        self.data_fetcher = TennisDataFetcher(session, admin_url)
        self.stats_processor = StatisticsProcessor()

    async def analyze_match(self, today, match_vs, player_id, match_id, last_flag):
        tour_now = await self.data_fetcher.fetch_tournament_data(match_id)

        data = await self.data_fetcher.fetch_player_activity(player_id, match_id, 1)
        last_10_winAB, last_50_winAB, last_12m_winAB_all, winAB_all = self.stats_processor.calculate_win_percentages(data)

        show_class = data.find(id="activity-table").find_all(class_="show")
        nb_match_last_month = 0
        date_i = 1
        one_month = 2629800
        pAB_matchs = data.find_all(class_="activity-clickthroughs no-link")
        m_i = 0
        min_tour = 0
        per_first_serve, points_first_serve, per_save_bp = 0, 0, 0

        for i in range(2, len(show_class)):
            if show_class[i].text != "Date":
                if today - datetime.strptime(show_class[date_i].text, "%b %d %Y").timestamp() <= one_month:
                    nb_match_last_month += 1
            else:
                if m_i + nb_match_last_month != 0:
                    date_i += m_i + nb_match_last_month + 1
                else:
                    date_i = i + 1
                if show_class[date_i].text == "Date":
                    date_i += 1
                d = None
                while d is None:
                    try:
                        d = datetime.strptime(show_class[date_i].text, "%b %d %Y").timestamp()
                    except ValueError:
                        date_i -= 1
                if today - datetime.strptime(show_class[date_i].text, "%b %d %Y").timestamp() > one_month:
                    break
            if tour_now in data.find(id="activity-table").find("a").text:
                try:
                    new_min_tour, new_per_first_serve, new_points_first_serve, new_per_save_bp = await self.stats_processor.process_match_statistics(self.data_fetcher, pAB_matchs, tour_now, m_i)
                    min_tour += new_min_tour
                    if m_i == 1 and "Qualifying" not in data.text:
                        per_first_serve, points_first_serve, per_save_bp = new_per_first_serve, new_points_first_serve, new_per_save_bp
                except:
                    pass
                m_i += 1

        data = await self.data_fetcher.fetch_player_activity(player_id, match_id, 2)
        last_12m_winAB_sur, winAB_sur = self.stats_processor.calculate_win_percentages(data)[2:]

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

        return match_vs

async def last_matchs(session, today, match_vs, admin_url, player_id, match_id, last_flag):
    analyzer = TennisMatchAnalyzer(session, admin_url)
    return await analyzer.analyze_match(today, match_vs, player_id, match_id, last_flag)