from requests_html import HTMLSession
from bs4 import BeautifulSoup

def odds_match(match_vs, indice_tab) :
    session = HTMLSession()
    resp = session.get("https://www.oddsportal.com/search/" + match_vs[2].split(" ")[-1])
    resp.html.render()
    driver = BeautifulSoup(resp.html.html, "lxml")
    try :
        match = driver.find_all(class_="flex w-full items-center") # relative w-full flex-col flex text-xs leading-[16px] min-w-[0] gap-1 next-m:!flex-row next-m:!gap-2 justify-center
        odds = [] 
        for elem in driver.find_all(class_="gradient-green-added-border") :
            if elem['class'][0] == "height-content" :
                if "-" in elem.text :
                    odds.append(round(100/int(elem.text.replace("-",""))+1, 2))
                elif "+" in elem.text :
                    odds.append(round(int(elem.text.replace("+",""))/100+1, 2))
                else :
                    odds.append(elem.text)
        match = match[0].text.strip()
        if match.find(match_vs[2].split(" ")[-1]) < match.find(match_vs[3].split(" ")[-1]) :
            if float(odds[0]) > float(odds[1]) :
                indice_tab[20] = 20
                indice_tab[21] = 0
            else :
                indice_tab[20] = 10
                indice_tab[21] = 10
            match_vs[38] = odds[0]
            match_vs[39] = odds[1]
        else :
            if float(odds[1]) > float(odds[0]) :
                indice_tab[20] = 20
                indice_tab[21] = 0
            else :
                indice_tab[20] = 10
                indice_tab[21] = 10
            match_vs[38] = odds[1]
            match_vs[39] = odds[0]
    except :
        resp = session.get("https://www.oddsportal.com/search/" + match_vs[3].split(" ")[-1])
        resp.html.render()
        driver = BeautifulSoup(resp.html.html, "lxml")
        try :
            match = driver.find_all(class_="flex w-full items-center") # relative w-full flex-col flex text-xs leading-[16px] min-w-[0] gap-1 next-m:!flex-row next-m:!gap-2 justify-center
            odds = [] 
            for elem in driver.find_all(class_="gradient-green-added-border") :
                if elem['class'][0] == "height-content" :
                    if "-" in elem.text :
                        odds.append(round(100/int(elem.text.replace("-",""))+1, 2))
                    elif "+" in elem.text :
                        odds.append(round(int(elem.text.replace("+",""))/100+1, 2))
                    else :
                        odds.append(elem.text)
            match = match[0].text.strip()
            if match.find(match_vs[2].split(" ")[-1]) < match.find(match_vs[3].split(" ")[-1]) :
                if float(odds[0]) > float(odds[1]) :
                    indice_tab[20] = 20
                    indice_tab[21] = 0
                else :
                    indice_tab[20] = 10
                    indice_tab[21] = 10
                match_vs[38] = odds[0]
                match_vs[39] = odds[1]
            else :
                if float(odds[1]) > float(odds[0]) :
                    indice_tab[20] = 20
                    indice_tab[21] = 0
                else :
                    indice_tab[20] = 10
                    indice_tab[21] = 10
                match_vs[38] = odds[1]
                match_vs[39] = odds[0]
        except :
            pass
        
    if float(match_vs[36]) < float(match_vs[37]) :
        indice_tab[22] = 40
    elif float(match_vs[37]) > float(match_vs[36]) :
        indice_tab[23] = 40
    else :
        indice_tab[22] = 20
        indice_tab[23] = 20

    session.close()