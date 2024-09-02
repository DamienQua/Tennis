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

async def process_match(session, header, m, tournaments, elo_data, rate_limit, already):
    if not(("2024" in m) and (any(subword in m for subword in ("atp", "wta", "masters"))) and not ("/q/" in m or "tba-tba" in m)) or m in already:
        if "fruhvirtova" not in m and "noskova" not in m and "efremova" not in m and "andreeva" not in m and "krueger" not in m:
            return None
    
    start = time.perf_counter()
    
    try:
        async with rate_limit:
            m_i = await analyze_match(session, header, m, tournaments, elo_data)
    except aiohttp.ClientError:
        print("Connection error, retrying...")
        await asyncio.sleep(1)
        return None

    m_i += ", " + m 
    print("Match : ", m_i)
    print("Time elapsed : ", round(time.perf_counter() - start, 2), " sec")
    return m_i

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
        
        for m in mtch:
            elo_data = atp_elo + '\n' + wta_elo if ("atp" in m or ("wta" not in m and "masters" in m)) else wta_elo + '\n' + atp_elo
            m_i = await process_match(session, session_config.header, m, tournaments, elo_data, session_config.rate_limit, already)
            
            if m_i:
                matchs += m_i + "\n"
                matchs_tab[i] = m_i
                i += 1
                update_match_files(m_i, matchs)

    print(matchs)

if __name__ == "__main__":
    asyncio.run(main())