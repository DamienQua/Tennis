import aiohttp
import asyncio
import re

async def fetch_odds(session, player):
    url = f"https://www.oddsportal.com/search/{player}"
    max_retries = 3
    delay = 0.25

    for attempt in range(max_retries):
        async with session.get(url) as resp:
            if resp.status == 200:
                await asyncio.sleep(delay)  # Wait for content to load
                return await resp.text()
            else:
                print(f"Attempt {attempt + 1} failed. Status: {resp.status}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
    
    raise Exception(f"Unable to load page for {player} after {max_retries} attempts")

def extract_data(text):
    match_name = re.search(r'&quot;name&quot;:&quot;(.*?)&quot;', text)
    name = match_name.group(1) if match_name else None
    odds = re.findall(r'&quot;avgOdds&quot;:([\d.]+)', text)
    return name, odds[0] if len(odds) > 0 else None, odds[1] if len(odds) > 1 else None

async def process_odds(html, match_vs, indice_tab, player_index):
    name, odds1, odds2 = extract_data(html)
    if name and odds1 and odds2:
        odds = [float(odds1), float(odds2)]
        if name.find(match_vs[2].split(" ")[-1]) < name.find(match_vs[3].split(" ")[-1]):
            match_vs[38], match_vs[39] = odds[1], odds[0]
        else:
            match_vs[38], match_vs[39] = odds[0], odds[1]
        
        if float(match_vs[38]) > float(match_vs[39]):
            indice_tab[20], indice_tab[21] = 20, 0
        else:
            indice_tab[20], indice_tab[21] = 10, 10
        
        return True
    return False

async def odds_match(match_vs, indice_tab):
    async with aiohttp.ClientSession() as session:
        player1, player2 = match_vs[2].split(" ")[-1], match_vs[3].split(" ")[-1]
        html1, html2 = await asyncio.gather(
            fetch_odds(session, player1),
            fetch_odds(session, player2)
        )
        
        success = await process_odds(html1, match_vs, indice_tab, 2)
        if not success:
            success = await process_odds(html2, match_vs, indice_tab, 3)
        
        if float(match_vs[36]) < float(match_vs[37]):
            indice_tab[22], indice_tab[23] = 40, 0
        elif float(match_vs[37]) > float(match_vs[36]):
            indice_tab[22], indice_tab[23] = 0, 40
        else:
            indice_tab[22], indice_tab[23] = 20, 20

    return match_vs, indice_tab