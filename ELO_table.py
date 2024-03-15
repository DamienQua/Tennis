import requests
from bs4 import BeautifulSoup 

def ELO_table(m_w) :
    table = ""
    header = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
    url = "https://tennisabstract.com/reports/" + m_w.lower() + "_elo_ratings.html"
    #Create a handle, page, to handle the contents of the website
    page = requests.get(url, headers=header)
    soup = BeautifulSoup(page.content, 'lxml')
    tr_elements = soup.find_all("tr")[5:]

    with open(m_w + "_ELO.txt", "w") as f:
        for tr in tr_elements :
            td = tr.find_all("td")
            table += td[1].text.replace("\xa0", " ") + " " + td[9].text + " " + td[10].text + " " + td[11].text + "\n"
            f.write(table)
    return table