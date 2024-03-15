from math import ceil

def compare_indice(indice_tab, match_vs) :
    comp = [0, 0, 0]
    for k in range(len(indice_tab)) :
        if k in (0, 1, 4, 20, 22) :
            if indice_tab[k] > indice_tab[k+1] :
                comp[0] += 20
            elif indice_tab[k] < indice_tab[k+1] :
                comp[1] += 20
        if k in (6, 8, 10, 12, 14, 16, 18) :
            if indice_tab[k] > indice_tab[k+1] :
                comp[0] += 5*ceil((indice_tab[k]-indice_tab[k+1])/10)
            if indice_tab[k] < indice_tab[k+1] :
                comp[1] += 5*ceil((indice_tab[k+1]-indice_tab[k])/10)
    
    comp[2] = comp[0] + comp[1]

    if match_vs[36] < match_vs[37] :
        if 0 <= comp[0]/comp[2] < 0.25 :
            indice_tab[24] = 0.5
        elif 0.25 <= comp[0]/comp[2] < 0.5 :
            indice_tab[24] = 1
        elif 0.5 <= comp[0]/comp[2] < 0.75 :
            indice_tab[24] = 2
        else :
            indice_tab[24] = 3
    elif match_vs[37] > match_vs[36] :
        if 0 <= comp[1]/comp[2] < 0.25 :
            indice_tab[24] = 0.5
        elif 0.25 <= comp[1]/comp[2] < 0.5 :
            indice_tab[24] = 1
        elif 0.5 <= comp[1]/comp[2] < 0.75 :
            indice_tab[24] = 2
        else :
            indice_tab[24] = 3
    else :
        indice_tab[24] = 1