from math import ceil, floor

def compare_players(match_vs) :
    comp = [0, 0, 0]
    for k in range(4, 25) :
        if k in (4, 8, 19) :
            if k == 4 :
                if float(match_vs[k]) < float(match_vs[k+1]) :
                    comp[0] += 5*floor((float(match_vs[k+1])-float(match_vs[k])-1)/10)
                if float(match_vs[k]) > float(match_vs[k+1]) :
                    comp[1] += 5*floor((float(match_vs[k])-float(match_vs[k+1])-1)/10)
            elif k == 8 :
                if float(match_vs[k]) > float(match_vs[k+1]) :
                    comp[0] += 3*ceil((float(match_vs[k])-float(match_vs[k+1]))/10)
                if float(match_vs[k]) < float(match_vs[k+1]) :
                    comp[1] += 3*ceil((float(match_vs[k+1])-float(match_vs[k]))/10)    
            else :
                if float(match_vs[k]) > float(match_vs[k+11]) :
                    comp[0] += 30
                elif float(match_vs[k]) == float(match_vs[k+11]) :
                    comp[0] += 30
                    comp[1] += 30
                else :
                    comp[1] += 30
        if k in (6, 14, 20, 21) :
            if k == 6 :
                if float(match_vs[k]) > float(match_vs[k+1]) :
                    comp[0] += ceil((float(match_vs[k])-float(match_vs[k+1]))/10)
                if float(match_vs[k]) < float(match_vs[k+1]) :
                    comp[1] += ceil((float(match_vs[k+1])-float(match_vs[k]))/10)
            else :
                if float(match_vs[k]) > float(match_vs[k+11]) :
                    if k == 14 :
                        comp[0] += 10
                    else :
                        comp[1] += 10
                elif float(match_vs[k]) == float(match_vs[k+11]) :
                    comp[0] += 10
                    comp[1] += 10
                else :
                    if k == 14 :
                        comp[1] += 10
                    else :
                        comp[0] += 10
        if k in (10, 12, 15, 16, 17, 18, 22, 23, 24) :
            if k in (10, 12) :
                if float(match_vs[k]) > float(match_vs[k+1]) :
                    comp[0] += 5*ceil((float(match_vs[k])-float(match_vs[k+1]))/10)
                if float(match_vs[k]) < float(match_vs[k+1]) :
                    comp[1] += 5*ceil((float(match_vs[k+1])-float(match_vs[k]))/10)
            else :
                if float(match_vs[k]) > float(match_vs[k+11]) :
                    comp[0] += 20
                elif float(match_vs[k]) == float(match_vs[k+11]) :
                    comp[0] += 20
                    comp[1] += 20
                else :
                    comp[1] += 20
    
    comp[2] = comp[0] + comp [1]
    trj = 0.9

    if comp[0] <= comp[1] :
        oddsA = round(trj*comp[2]/(comp[0]+1e-3), 2)
        oddsB = round(1/(1/trj-1/oddsA), 2)
    else :
        oddsB = round(trj*comp[2]/(comp[1]+1e-3), 2)
        oddsA = round(1/(1/trj-1/oddsB), 2)

    match_vs[36] = oddsA
    match_vs[37] = oddsB