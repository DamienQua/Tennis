import aiohttp
from bs4 import BeautifulSoup
import re
from indice_confiance import indice_confiance
from h2h_stats import H2HStats, DateUtils

class MatchContext:
    def __init__(self, surface, admin_url, header, match_id):
        self.surface = surface
        self.admin_url = admin_url
        self.header = header
        self.match_id = match_id

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