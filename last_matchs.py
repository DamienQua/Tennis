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

    async def fetch_player_activity(self, player_id, match_id, activity_option, odds_option = "0"):
        pAB_param = {
            "action": "playerActivity",
            "activityOffset": "0",
            "basic-activity-option": str(activity_option),
            "odds": str(odds_option),
            "filterType": "basic",
            "playerID": player_id,
            "matchID": match_id
        }
        data_html = await self.fetch_data(self.admin_url, pAB_param)
        return BeautifulSoup(data_html, "lxml")
    
    async def fetch_player_activity_with_odds(self, player_id, match_id, activity_option, flag, favorite):
        odds_option = "5" if favorite[flag] == 1 else "6"
        return await self.fetch_player_activity(player_id, match_id, activity_option, odds_option)


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

    async def analyze_match(self, today, match_vs, player_id, match_id, last_flag, favorite):
        tour_now = await self.fetch_tournament_data(match_id)
        win_percentages = await self.calculate_win_percentages(player_id, match_id)
        match_stats = await self.process_match_statistics(player_id, match_id, tour_now)
        nb_match_last_month = await self.calculate_matches_last_month(today, player_id, match_id)

        self.update_match_vs(match_vs, win_percentages, match_stats, nb_match_last_month, last_flag)

        odds_spread = await self.data_fetcher.fetch_player_activity_with_odds(player_id, match_id, 1, last_flag, favorite)
        odds_data = odds_spread.find(class_="stats-table").find_all("tr")[2].find_all("td")[1].text.strip().split()
        
        odds_index = 2 if favorite[last_flag] == 1 else 0
        odds_value = float(odds_data[odds_index])
        
        match_vs[42 + last_flag] = -odds_value if favorite[last_flag] == 1 else odds_value

        return match_vs

    async def fetch_tournament_data(self, match_id):
        return await self.data_fetcher.fetch_tournament_data(match_id)

    async def calculate_win_percentages(self, player_id, match_id):
        data = await self.data_fetcher.fetch_player_activity(player_id, match_id, 1)
        all_percentages = self.stats_processor.calculate_win_percentages(data)

        data = await self.data_fetcher.fetch_player_activity(player_id, match_id, 2)
        surface_percentages = self.stats_processor.calculate_win_percentages(data)[2:]

        return all_percentages + surface_percentages

    async def process_match_statistics(self, player_id, match_id, tour_now):
        data = await self.data_fetcher.fetch_player_activity(player_id, match_id, 1)
        pAB_matchs = data.find_all(class_="activity-clickthroughs no-link")

        min_tour, per_first_serve, points_first_serve, per_save_bp = 0, 0, 0, 0

        for m_i, match in enumerate(pAB_matchs):
            if not self.is_match_in_tournament(match, tour_now):
                break
            new_stats = await self.get_match_statistics(data, pAB_matchs, tour_now, m_i)
            min_tour, per_first_serve, points_first_serve, per_save_bp = self.update_statistics(
                new_stats, min_tour, per_first_serve, points_first_serve, per_save_bp, m_i, data
            )

        return min_tour, per_first_serve, points_first_serve, per_save_bp

    def update_statistics(self, new_stats, min_tour, per_first_serve, points_first_serve, per_save_bp, m_i, data):
        if new_stats:
            min_tour += new_stats[0]
            if m_i == 0 and "Qualifying" not in data.text:
                per_first_serve, points_first_serve, per_save_bp = new_stats[1:]
        return min_tour, per_first_serve, points_first_serve, per_save_bp

    def is_match_in_tournament(self, match, tour_now):
        return tour_now.lower().replace(" ", "-") in match.contents[1]["href"]

    async def get_match_statistics(self, data, pAB_matchs, tour_now, m_i):
        try:
            return await self.stats_processor.process_match_statistics(self.data_fetcher, pAB_matchs, tour_now, m_i)
        except:
            return None

    async def calculate_matches_last_month(self, today, player_id, match_id):
        data = await self.data_fetcher.fetch_player_activity(player_id, match_id, 1)
        show_class = data.find(id="activity-table").find_all(class_="show")
        
        nb_match_last_month = 0
        date_i = 1
        one_month = 2629800

        for i in range(2, len(show_class)):
            if self.is_valid_date(show_class, i, today, date_i, one_month):
                nb_match_last_month += 1
            else:
                date_i = self.update_date_index(show_class, i, date_i, nb_match_last_month)
                if not self.is_within_last_month(show_class, date_i, today, one_month):
                    break

        return nb_match_last_month

    def is_valid_date(self, show_class, i, today, date_i, one_month):
        return show_class[i].text != "Date" and today - datetime.strptime(show_class[date_i].text, "%b %d %Y").timestamp() <= one_month

    def is_within_last_month(self, show_class, date_i, today, one_month):
        return today - datetime.strptime(show_class[date_i].text, "%b %d %Y").timestamp() <= one_month

    def update_date_index(self, show_class, i, date_i, nb_match_last_month):
        date_i = self.adjust_date_index(show_class, i, date_i, nb_match_last_month)
        return self.find_valid_date_index(show_class, date_i)

    def adjust_date_index(self, show_class, i, date_i, nb_match_last_month):
        if nb_match_last_month != 0:
            return date_i + nb_match_last_month + 1
        return i + 1 if show_class[date_i].text == "Date" else date_i

    def find_valid_date_index(self, show_class, date_i):
        while True:
            try:
                datetime.strptime(show_class[date_i].text, "%b %d %Y")
                return date_i
            except ValueError:
                date_i -= 1

    def update_match_vs(self, match_vs, win_percentages, match_stats, nb_match_last_month, last_flag):
        offset = 14 + 11 * last_flag
        match_vs[offset:offset+11] = win_percentages + [nb_match_last_month] + list(match_stats)

async def last_matchs(session, today, match_vs, admin_url, player_id, match_id, last_flag, favorite):
    analyzer = TennisMatchAnalyzer(session, admin_url)
    return await analyzer.analyze_match(today, match_vs, player_id, match_id, last_flag, favorite)