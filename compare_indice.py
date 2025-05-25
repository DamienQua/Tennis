"""
Compares indices and calculates a comparative score based on specific and range-based index comparisons.

This module provides functionality to:
- Compare specific indices in a given index table
- Compare ranges of indices 
- Calculate a comparative score based on the comparisons
- Determine a final index value for a specific position

The main components are:
- IndiceComparator: Handles the core comparison logic
- calculate_indice_24: Calculates the final index based on comparison results
- compare_indice: Top-level function to perform index comparisons
"""

from math import ceil

class IndiceComparator:
    def __init__(self, indice_tab):
        self.indice_tab = indice_tab
        self.comp = [0, 0, 0]

    def compare_indices(self):
        self._compare_specific_indices()
        self._compare_range_indices()
        self.comp[2] = self.comp[0] + self.comp[1]
        return self.comp

    def _compare_specific_indices(self):
        for k in (0, 1, 4, 20, 22):
            if self.indice_tab[k] > self.indice_tab[k+1]:
                self.comp[0] += 20
            elif self.indice_tab[k] < self.indice_tab[k+1]:
                self.comp[1] += 20

    def _compare_range_indices(self):
        for k in (6, 8, 10, 12, 14, 16, 18):
            if self.indice_tab[k] > self.indice_tab[k+1]:
                self.comp[0] += 5*ceil((self.indice_tab[k]-self.indice_tab[k+1])/10)
            if self.indice_tab[k] < self.indice_tab[k+1]:
                self.comp[1] += 5*ceil((self.indice_tab[k+1]-self.indice_tab[k])/10)

def calculate_indice_24(comp, match_vs):
    if match_vs[36] < match_vs[37]:
        return _calculate_indice_24_helper(comp[0], comp[2])
    elif match_vs[37] > match_vs[36]:
        return _calculate_indice_24_helper(comp[1], comp[2])
    else:
        return 1

def _calculate_indice_24_helper(comp_value, comp_total):
    ratio = comp_value / comp_total
    if 0 <= ratio < 0.25:
        return 0.5
    elif 0.25 <= ratio < 0.5:
        return 1
    elif 0.5 <= ratio < 0.75:
        return 2
    else:
        return 3

def compare_indice(indice_tab, match_vs):
    comparator = IndiceComparator(indice_tab)
    comp = comparator.compare_indices()
    indice_tab[24] = calculate_indice_24(comp, match_vs)