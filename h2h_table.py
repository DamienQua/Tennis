import aiohttp
from bs4 import BeautifulSoup
import re
from indice_confiance import indice_confiance
from h2h_stats import H2HStats, DateUtils
from variables import indice_tab

class MatchContext:
    def __init__(self, surface, admin_url, header, match_id):
        self.surface = surface
        self.admin_url = admin_url
        self.header = header
        self.match_id = match_id

async def fetch_data(session, url, data=None):
    async with session.post(url, data=data) as response:
        return await response.text()

class H2HDataProcessor:
    def __init__(self, data, match_vs):
        self.data = data
        self.match_vs = match_vs
        self.stats = H2HStats(match_vs[2], match_vs[3])
        self.go = ""
        self.flag = 0

    def process_h2h_data(self):
        self._process_h2h_count()
        self._process_h2h_matches()
        self._calculate_percentages()

    def _process_h2h_count(self):
        if "tied" in self.data.text:
            ind = 1
        else:
            ind = 0

        for i in range(2):
            self.stats.h2h_nb += int(self.data.text.strip().split("series ")[1].split(" ")[ind].split("-")[i].split("\n")[0])

        if self.stats.h2h_nb > 0:
            for i in range(2):
                self.match_vs[i+6] = round(100*int(self.data.text.strip().split("series ")[1].split(" ")[ind].split("-")[i].split("\n")[0])/self.stats.h2h_nb, 2)
        else:
            self.match_vs[6:14] = [0] * 8

    def _process_h2h_matches(self):
        h2h_tr = self.data.find(class_="h2h-matches").find_all("tr")[1:]
        for tr in h2h_tr:
            date_ms = DateUtils.parse_date(tr.text.strip().split("\t")[0].strip())
            surface_m = tr.text.strip().split("\n")[5].strip().split(",")[0]
            winner = re.sub("[\(\[].*?[\)\]]", "", tr.text.strip().split("\n")[7].strip()).split(" d")[0].strip()
            try:
                score = re.sub("[\(\[].*?[\)\]]", "", tr.text.strip().split("\n")[9].strip()).replace("ret."," ").replace("w/o", "").strip()
            except:
                score = "0-0 0-0"

            self.stats.update_stats(winner, date_ms, surface_m, score)

            if self.go == "" and surface_m in tr.text:
                self.go = tr.find_all("a")[-1]["href"]
                self.flag = 0 if winner == self.match_vs[2] else 1

    def _calculate_percentages(self):
        percentages = self.stats.calculate_percentages()
        self.match_vs[8:14] = percentages["last_year"] + percentages["surface"] + percentages["games"]

async def h2h_table(data, match_vs, session, match_context: MatchContext):
    processor = H2HDataProcessor(data, match_vs)
    processor.process_h2h_data()

    global indice_tab
    if processor.stats.winA_sur > 0:
        indice_tab[4] = 2*indice_tab[1]
    if processor.stats.winB_sur > 0:
        indice_tab[5] = 2*indice_tab[3]

    if processor.go != "":
        await indice_confiance(session, match_context.admin_url, "", match_context.match_id, match_context.surface, processor.flag, "Tactique", processor.go)

    return match_vs