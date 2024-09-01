import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
import re
from indice_confiance import indice_confiance

class MatchContext:
    def __init__(self, surface, admin_url, header, match_id):
        self.surface = surface
        self.admin_url = admin_url
        self.header = header
        self.match_id = match_id

class DateUtils:
    @staticmethod
    def parse_date(date_str):
        return datetime.strptime(date_str.strip(), "%b %d %Y").timestamp()

    @staticmethod
    def is_within_last_year(date_ms):
        today = datetime.now().timestamp()
        year_ms = 365.25 * 24 * 3600
        return today - date_ms <= year_ms

class H2HStats:
    def __init__(self, player_a, player_b):
        self.player_a = player_a
        self.player_b = player_b
        self.winA_all = self.winB_all = 0
        self.winA_y = self.winB_y = 0
        self.winA_sur = self.winB_sur = 0
        self.winA_G = self.winB_G = 0
        self.h2h_nb = self.h2h_y = 0

    def update_stats(self, winner, date_ms, surface, score):
        self.h2h_nb += 1
        if winner == self.player_a:
            self._update_player_a_stats(date_ms, surface, score)
        else:
            self._update_player_b_stats(date_ms, surface, score)

    def _update_player_a_stats(self, date_ms, surface, score):
        self.winA_all += 1
        if DateUtils.is_within_last_year(date_ms):
            self.winA_y += 1
            self.h2h_y += 1
        if surface in score:
            self.winA_sur += 1
        self._update_game_stats(score, 0)

    def _update_player_b_stats(self, date_ms, surface, score):
        self.winB_all += 1
        if DateUtils.is_within_last_year(date_ms):
            self.winB_y += 1
            self.h2h_y += 1
        if surface in score:
            self.winB_sur += 1
        self._update_game_stats(score, 1)

    def _update_game_stats(self, score, loser_index):
        for set_score in score.split(" "):
            try:
                self.winA_G += int(set_score.split("-")[loser_index])
                self.winB_G += int(set_score.split("-")[1-loser_index])
            except:
                pass

    def calculate_percentages(self):
        return {
            "all_time": self._calculate_percentage(self.winA_all, self.winB_all),
            "last_year": self._calculate_percentage(self.winA_y, self.winB_y),
            "surface": self._calculate_percentage(self.winA_sur, self.winB_sur),
            "games": self._calculate_percentage(self.winA_G, self.winB_G)
        }

    def _calculate_percentage(self, wins_a, wins_b):
        total = wins_a + wins_b
        return (round(100 * wins_a / total, 2), round(100 * wins_b / total, 2)) if total > 0 else (0, 0)

async def fetch_data(session, url, data=None):
    async with session.post(url, data=data) as response:
        return await response.text()

async def h2h_table(data, match_vs, session, indice_tab, match_context: MatchContext):
    h2h_tr = data.find(class_="h2h-matches").find_all("tr")[1:]
    stats = H2HStats(match_vs[2], match_vs[3])
    go, flag = "", 0

    if "tied" in data.text:
        ind = 1
    else:
        ind = 0

    for i in range(2):
        stats.h2h_nb += int(data.text.strip().split("series ")[1].split(" ")[ind].split("-")[i].split("\n")[0])

    if stats.h2h_nb > 0:
        for i in range(2):
            match_vs[i+6] = round(100*int(data.text.strip().split("series ")[1].split(" ")[ind].split("-")[i].split("\n")[0])/stats.h2h_nb, 2)

        for tr in h2h_tr:
            date_ms = DateUtils.parse_date(tr.text.strip().split("\t")[0].strip())
            surface_m = tr.text.strip().split("\n")[5].strip().split(",")[0]
            winner = re.sub("[\(\[].*?[\)\]]", "", tr.text.strip().split("\n")[7].strip()).split(" d")[0].strip()
            try:
                score = re.sub("[\(\[].*?[\)\]]", "", tr.text.strip().split("\n")[9].strip()).replace("ret."," ").replace("w/o", "").strip()
            except:
                score = "0-0 0-0"

            stats.update_stats(winner, date_ms, surface_m, score)

            if go == "" and surface_m in tr.text:
                go = tr.find_all("a")[-1]["href"]
                flag = 0 if winner == match_vs[2] else 1

        percentages = stats.calculate_percentages()
        match_vs[8:14] = percentages["last_year"] + percentages["surface"] + percentages["games"]

    else:
        match_vs[6:14] = [0] * 8

    if stats.winA_sur > 0:
        indice_tab[4] = 2*indice_tab[1]
    if stats.winB_sur > 0:
        indice_tab[5] = 2*indice_tab[3]

    if go != "":
        await indice_confiance(indice_tab, session, match_context.admin_url, "", match_context.match_id, match_context.surface, flag, "Tactique", go)   