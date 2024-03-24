from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
from requests_html import HTMLSession
from bs4 import BeautifulSoup
from indice_confiance import indice_confiance

def odds_match(match_vs, indice_tab) :
    session = HTMLSession()
    resp = session.get("https://www.oddsportal.com/search/" + match_vs[2])
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
        driver.get("https://www.oddsportal.com/search/" + match_vs[3])
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

    ''' url = "oddsportal.com/search/"
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(options=chrome_options)
    driver.get("https://www.oddsportal.com/search/" + match_vs[2])
    time.sleep(0.1)
    try :
        match = driver.find_elements_by_class_name("table-participant")
        i = 0
        while "/" in match[i].text :
            i += 1
        match = match[i].text.strip()
        if match.find(match_vs[2].split(" ")[-1]) < match.find(match_vs[3].split(" ")[-1]) :
            match_vs.append(float(driver.find_elements_by_class_name("odds-nowrp")[2*i].text))
            match_vs.append(float(driver.find_elements_by_class_name("odds-nowrp")[2*i+1].text))
        else :
            match_vs.append(float(driver.find_elements_by_class_name("odds-nowrp")[2*i+1].text))
            match_vs.append(float(driver.find_elements_by_class_name("odds-nowrp")[2*i].text))
    except ValueError :
        driver.get("https://www.oddsportal.com/search/" + match_vs[3])
        try :
            match = driver.find_element_by_class_name("table-participant").text.strip()
            i = 0
            while "/" in match[i].text :
                i += 1
            match = match[i].text.strip()
            if match.find(match_vs[2].split(" ")[-1]) < match.find(match_vs[3].split(" ")[-1]) :
                match_vs.append(float(driver.find_elements_by_class_name("odds-nowrp")[2*i].text))
                match_vs.append(float(driver.find_elements_by_class_name("odds-nowrp")[2*i+1].text))
            else :
                match_vs.append(float(driver.find_elements_by_class_name("odds-nowrp")[2*i+1].text))
                match_vs.append(float(driver.find_elements_by_class_name("odds-nowrp")[2*i].text))
        except ValueError :
                match_vs.append(0)
                match_vs.append(0)
    driver.close() '''