"""Tests unitaires pour compare_players, compare_indice, H2H et MatchStatisticsAnalyzer."""

import unittest
from bs4 import BeautifulSoup
from analysis.compare_indice import compare_indice
from analysis.compare_players import compare_players
from analysis.h2h_table import H2HDataProcessor
from analysis.match_statistics_analyzer import MatchStatisticsAnalyzer
from core.models import ConfidenceMetrics, H2HMetrics, MatchAnalysisData, PlayerStats


class TestComparators(unittest.TestCase):
    """Unit tests for player attribute and confidence indices comparators."""

    def test_compare_players(self):
        match = MatchAnalysisData(
            match_url="https://tennisinsight.com/match/1/2026-atp/r16/a-vs-b",
            surface="Hard",
            player_a=PlayerStats(name="Player A", ranking=10),
            player_b=PlayerStats(name="Player B", ranking=20),
            h2h=H2HMetrics(all_time=(50.0, 40.0)),
        )
        compare_players(match)
        self.assertGreater(match.player_a.model_odds, 0.0)
        self.assertGreater(match.player_b.model_odds, 0.0)
        self.assertLess(match.player_a.model_odds, match.player_b.model_odds)

    def test_indice_comparator(self):
        match = MatchAnalysisData(
            match_url="https://tennisinsight.com/match/2/2026-atp/r16/a-vs-b",
            player_a=PlayerStats(name="Player A", model_odds=1.50),
            player_b=PlayerStats(name="Player B", model_odds=2.50),
            confidence=ConfidenceMetrics(motivation_a=100.0, motivation_b=50.0),
        )
        final_idx = compare_indice(match)
        self.assertGreater(final_idx, 0.0)
        self.assertEqual(match.confidence.final_index, final_idx)

    def test_h2h_empty_data_does_not_raise(self):
        match = MatchAnalysisData(
            match_url="https://tennisinsight.com/match/3/2026-atp/r16/a-vs-b",
            surface="Hard",
            player_a=PlayerStats(name="Player A"),
            player_b=PlayerStats(name="Player B"),
        )
        soup = BeautifulSoup("", "lxml")
        proc = H2HDataProcessor(soup, match)
        proc.process_h2h_data()
        self.assertEqual(match.h2h.all_time, (0.0, 0.0))

    def test_h2h_truncated_row_details(self):
        row = BeautifulSoup("<tr><td>Nov 01 2026\nLine 1</td></tr>", "lxml")
        _, surf, winner, score = H2HDataProcessor._extract_match_details(row)
        self.assertEqual(surf, "")
        self.assertEqual(winner, "")
        self.assertEqual(score, "0-0 0-0")

    def test_match_statistics_analyzer_empty_data(self):
        analyzer = MatchStatisticsAnalyzer()
        empty_soup = BeautifulSoup("", "lxml")
        stats = analyzer.calculate_serve_return_stats(empty_soup, 0)
        self.assertEqual(len(stats), 12)
        self.assertEqual(stats[0], 0.0)
        tb_1, tb_2 = analyzer.calculate_tiebreak_stats(empty_soup)
        self.assertEqual(tb_1, 0.0)
        self.assertEqual(tb_2, 0.0)


if __name__ == "__main__":
    unittest.main()
