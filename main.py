import asyncio
import aiohttp
from bs4 import BeautifulSoup
import time
import numpy as np
from ELO_table import ELO_table
from analyze_match import analyze_match
from aiolimiter import AsyncLimiter
from collections import namedtuple

SessionConfig = namedtuple('SessionConfig', ['header', 'connector', 'rate_limit'])

class MatchProcessor:
    def __init__(self, session, header, rate_limit, already_processed):
        self.session = session
        self.header = header
        self.rate_limit = rate_limit
        self.already_processed = already_processed

    def should_process_match(self, match_url):
        return (("2024" in match_url) and 
                (any(subword in match_url for subword in ("atp", "wta", "masters"))) and 
                not ("/q/" in match_url or "tba-tba" in match_url) and 
                match_url not in self.already_processed)

    async def fetch_and_analyze(self, match_url, tournaments, elo_data):
        async with self.rate_limit:
            return await analyze_match(self.session, self.header, match_url, tournaments, elo_data)

    def format_result(self, match_info, match_url):
        return f"{match_info}, {match_url}"

    async def process(self, match_url, tournaments, elo_data):
        if not self.should_process_match(match_url):
            if "fruhvirtova" not in match_url and "noskova" not in match_url and "efremova" not in match_url and "andreeva" not in match_url and "krueger" not in match_url:
                return None

        start = time.perf_counter()

        try:
            match_info = await self.fetch_and_analyze(match_url, tournaments, elo_data)
        except aiohttp.ClientError:
            print("Connection error, retrying...")
            await asyncio.sleep(1)
            return None

        result = self.format_result(match_info, match_url)
        print("Match : ", result)
        print("Time elapsed : ", round(time.perf_counter() - start, 2), " sec")
        return result

async def fetch_data(session, url, method='get', data=None):
    if method == 'get':
        async with session.get(url) as response:
            return await response.text()
    elif method == 'post':
        async with session.post(url, data=data) as response:
            return await response.text()

def create_session_config():
    header = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
    conn = aiohttp.TCPConnector(limit=10)  # 10 simultaneous connections
    rate_limit = AsyncLimiter(10, 1)  # 10 requests per second
    return SessionConfig(header, conn, rate_limit)

def load_reviewed_matches():
    try:
        with open("Reviewed_Matchs.txt", "r") as f:
            return f.read()
    except:
        return ""

async def login(session):
    login_data = {"log": "", "pwd": ""}
    await fetch_data(session, "https://tennisinsight.com/wp-login.php", method='post', data=login_data)

async def fetch_match_previews(session):
    mtch_previews_html = await fetch_data(session, "https://tennisinsight.com/match-previews/")
    mtch_previews = BeautifulSoup(mtch_previews_html, "lxml")
    tournaments = np.array([tour.text for tour in mtch_previews.find_all(class_="heading-link") if any(x in tour.text for x in ["ATP", "WTA", "Masters"])])
    mtch = [m.a["href"] for m in mtch_previews.find_all(class_="match-row-link")]
    return tournaments, mtch

def update_match_files(m_i, matchs):
    with open("Reviewed_Matchs.txt", "a") as old:
        old.write(m_i + "\n")
    with open("Matchs.txt", "w") as new:
        new.write(matchs)

async def main():
    session_config = create_session_config()
    
    atp_elo = await ELO_table("ATP")
    wta_elo = await ELO_table("WTA")
    
    already = load_reviewed_matches()
    matchs = ""
    matchs_tab = np.chararray(256, itemsize=100, unicode=True)
    i = 0

    async with aiohttp.ClientSession(connector=session_config.connector, headers=session_config.header) as session:
        await login(session)
        tournaments, mtch = await fetch_match_previews(session)
        
        processor = MatchProcessor(session, session_config.header, session_config.rate_limit, already)
        
        for m in mtch:
            elo_data = atp_elo + '\n' + wta_elo if ("atp" in m or ("wta" not in m and "masters" in m)) else wta_elo + '\n' + atp_elo
            m_i = await processor.process(m, tournaments, elo_data)
            
            if m_i:
                matchs += m_i + "\n"
                matchs_tab[i] = m_i
                i += 1
                update_match_files(m_i, matchs)

    print(matchs)

if __name__ == "__main__":
    asyncio.run(main())