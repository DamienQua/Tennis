import unittest
import sys
import os
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from analysis.compare_players import compare_players
from analysis.compare_indice import compare_indice, IndiceComparator
from analysis.h2h_table import H2HDataProcessor
from bs4 import BeautifulSoup

class TestComparators(unittest.TestCase):
    """Unit tests for player attribute and confidence indices comparators."""
    def test_compare_players(self):
        match_vs = np.full(44, "0.0", dtype="<U100")
        match_vs[4] = "10"
        match_vs[5] = "20"
        match_vs[6] = "50.0"
        match_vs[7] = "40.0"
        match_vs[42] = "0.0"
        match_vs[43] = "0.0"
        compare_players(match_vs)
        # Verify odds were populated
        self.assertTrue(bool(match_vs[36]))
        self.assertTrue(bool(match_vs[37]))

    def test_indice_comparator(self):
        indice_tab = np.zeros(25)
        match_vs = np.full(44, "0", dtype="<U100")
        match_vs[36] = "1.50"
        match_vs[37] = "2.50"
        indice_tab[0] = 5.0
        indice_tab[1] = 2.0
        compare_indice(indice_tab, match_vs)
        self.assertGreater(indice_tab[24], 0)

    def test_h2h_empty_data_does_not_raise(self):
        match_vs = np.full(44, "", dtype="<U100")
        match_vs[1] = "Hard"
        match_vs[2] = "Player A"
        match_vs[3] = "Player B"
        soup = BeautifulSoup("", "lxml")
        proc = H2HDataProcessor(soup, match_vs)
        proc.process_h2h_data()
        self.assertEqual(match_vs[6], "0")

    def test_h2h_truncated_row_details(self):
        # Truncated row with only 2 lines
        row = BeautifulSoup("<tr><td>Nov 01 2026\nLine 1</td></tr>", "lxml")
        d_ms, surf, winner, score = H2HDataProcessor._extract_match_details(row)
        self.assertEqual(surf, "")
        self.assertEqual(winner, "")
        self.assertEqual(score, "0-0 0-0")

    def test_match_statistics_analyzer_empty_data(self):
        from analysis.match_statistics_analyzer import MatchStatisticsAnalyzer
        analyzer = MatchStatisticsAnalyzer()
        empty_soup = BeautifulSoup("", "lxml")
        stats = analyzer.calculate_serve_return_stats(empty_soup, 0)
        self.assertEqual(len(stats), 12)
        self.assertEqual(stats[0], 0.0)
        tb_1, tb_2 = analyzer.calculate_tiebreak_stats(empty_soup)
        self.assertEqual(tb_1, 0)
        self.assertEqual(tb_2, 0)

if __name__ == "__main__":
    unittest.main()
