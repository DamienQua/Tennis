import aiohttp
from bs4 import BeautifulSoup 
import functools

@functools.lru_cache(maxsize=None)
async def fetch_data(url, user_agent):
    headers = {'User-Agent': user_agent}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            return await response.text()

async def ELO_table(m_w):
    table = ""
    elo = ""
    user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
    url = "https://tennisabstract.com/reports/" + m_w.lower() + "_elo_ratings.html"
    
    content = await fetch_data(url, user_agent)
    soup = BeautifulSoup(content, 'lxml')
    tr_elements = soup.find_all("tr")[3:]

    with open(f"{m_w}_ELO.txt", "w") as f:
        for tr in tr_elements:
            td = tr.find_all("td")
            table = td[1].text.replace("\xa0", " ") + " " + td[9].text + " " + td[10].text + " " + td[11].text + "\n"
            f.write(table)
            elo += table
    
    return elo