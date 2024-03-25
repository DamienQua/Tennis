from ELO_table import ELO_table
from analyze_match import analyze_match
import requests
from bs4 import BeautifulSoup
import time
import numpy as np

def main() :
    header = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}

    atp_elo = ELO_table("ATP")
    wta_elo = ELO_table("WTA")
    #odds_vs = []
    already = ""
    matchs = ""
    matchs_tab = np.chararray(256, itemsize = 100, unicode = True)
    i, t_i = 0, 0
    try :
        with open("Reviewed_Matchs.txt", "r") as f:
            already += f.read()
    except :
        already = ""

    with requests.Session() as session :
        ti = session.post("https://tennisinsight.com/wp-login.php", {"log" : "", "pwd" : ""}, headers = header)
        mtch_previews = BeautifulSoup(session.get("https://tennisinsight.com/match-previews/").content, "lxml")
        tournaments = np.chararray(len(mtch_previews.find_all(class_="heading-link")), itemsize = 100, unicode = True)
        for tour in mtch_previews.find_all(class_="heading-link") :
            if "ATP" in tour.text or "WTA" in tour.text or "Masters" in tour.text :
                tournaments[t_i] = tour.text
                t_i += 1
        mtch = [m.a["href"] for m in mtch_previews.find_all(class_="match-row-link")]
        for m in mtch :
            if not(("2024" in m) and (any(subword in m for subword in ("atp", "wta", "masters"))) and not ("/q/" in m or "tba-tba" in m)) or m in already :
                if "fruhvirtova" not in m and "noskova" not in m and "efremova" not in m and "andreeva" not in m and "krueger" not in m :#and m not in already :
                    continue
            start = time.perf_counter()
            m_i = analyze_match(i, session, header, m, tournaments, atp_elo + '\n' + wta_elo if ("atp" in m or ("wta" not in m and "masters" in m)) else wta_elo + '\n' + atp_elo)
            m_i += ", " + m 
            matchs += m_i + "\n"
            matchs_tab[i] = m_i
            print("Match : ", matchs_tab[i])
            print("Temps écoulé : ", round(time.perf_counter() - start, 2), " sec")
            i += 1
            with open("Reviewed_Matchs.txt", "w") as old :
                already += "\n" + m_i
                old.write(already)
            with open("Matchs.txt", "w") as new :
                new.write(matchs)
        print(matchs)

if __name__ == "__main__" :
    main()