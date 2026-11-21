import unittest
import sys
import os
from math import isnan

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from analysis.last_matchs import TennisDataParser
from core.analyze_match import extract_player_ids
from bs4 import BeautifulSoup

class DummySoup:
    """Mock BeautifulSoup container for parsing tests."""
    def __init__(self, text):
        self.text = text

class TestTennisDataParser(unittest.TestCase):
    """Unit tests for TennisDataParser extraction and formatting methods."""
    def test_extract_single_percentage(self):
        val = TennisDataParser._extract_single_percentage("75.5%")
        self.assertEqual(val, 75.5)

        val_na = TennisDataParser._extract_single_percentage("N/A")
        self.assertTrue(isnan(val_na))

    def test_parse_win_percentages_empty(self):
        result = TennisDataParser.parse_win_percentages(None)
        self.assertEqual(result, [])

    def test_parse_win_percentages_with_text(self):
        raw = "Header Matches 50% Matches 65% (12 months) 70% (since 2000) 60%"
        result = TennisDataParser.parse_win_percentages(DummySoup(raw))
        self.assertEqual(result, [50.0, 65.0, 70.0, 60.0])

    def test_missing_windows_are_not_replaced_by_other_windows_or_zero(self):
        result = TennisDataParser.parse_win_percentages(DummySoup("(since 2000) 60%"))
        self.assertTrue(all(isnan(value) for value in result[:3]))
        self.assertEqual(result[3], 60.0)
        self.assertEqual(TennisDataParser._extract_single_percentage("0%"), 0.0)
        for value in ("N/A", "", "101%", "-1%", "NaN", "inf"):
            self.assertTrue(isnan(TennisDataParser._extract_single_percentage(value)))

    def test_failed_stats_collection_cannot_generate_model_odds(self):
        from analysis.last_matchs import TennisMatchAnalyzer
        from analysis.compare_players import compare_players
        from core.models import MatchAnalysisData, PlayerStats
        from unittest.mock import MagicMock

        percentages = TennisMatchAnalyzer(MagicMock()).extract_win_percentages(None, None)
        match = MatchAnalysisData(
            "test", player_a=PlayerStats(name="Alpha", ranking=1, elo=2000),
            player_b=PlayerStats(name="Beta", ranking=50, elo=1700),
        )
        match.player_a.win_pct_1y = percentages[2]
        match.player_a.win_pct_career_surface = percentages[5]
        compare_players(match)
        self.assertEqual(match.player_a.model_odds, 0)
        self.assertEqual(match.player_b.model_odds, 0)

    def test_missing_rankings_remain_invalid(self):
        from core.tournament_extractor import parse_player_rankings
        self.assertEqual(parse_player_rankings(BeautifulSoup("<div>Unknown</div>", "lxml")), [0, 0])

    def test_extract_player_ids_valid(self):
        html = (
            '<a href="/player/?playerid=54231">Player 1</a> and '
            '<a href="/player/?playerid=60865">Player 2</a>'
        )
        soup = BeautifulSoup(html, 'lxml')
        player_a, player_b = extract_player_ids(html, soup)
        self.assertEqual(player_a, '54231')
        self.assertEqual(player_b, '60865')

    def test_extract_player_ids_empty_or_error(self):
        player_a, player_b = extract_player_ids("")
        self.assertEqual(player_a, "")
        self.assertEqual(player_b, "")

        error_html = "<html><body><h1>503 Service Unavailable</h1></body></html>"
        player_a2, player_b2 = extract_player_ids(error_html)
        self.assertEqual(player_a2, "")
        self.assertEqual(player_b2, "")

    def test_extract_player_ids_single(self):
        html = '<a href="/player/?playerid=12345">Only One</a>'
        player_a, player_b = extract_player_ids(html)
        self.assertEqual(player_a, "12345")
        self.assertEqual(player_b, "")

    def test_player_extractor_clean_name_and_slug(self):
        from core.player_extractor import PlayerExtractor
        self.assertEqual(PlayerExtractor.clean_player_name("[1] Cori Gauff"), "Coco Gauff")
        p1, p2 = PlayerExtractor._names_from_slug(
            "https://tennisinsight.com/match/123/2026-event/r32/carlos-alcaraz-vs-jannik-sinner"
        )
        self.assertEqual(p1, "Carlos Alcaraz")
        self.assertEqual(p2, "Jannik Sinner")

    def test_tournament_extractor_surface(self):
        from core.tournament_extractor import TournamentExtractor
        url = "https://tennisinsight.com/match/123/2026-stockholm-atp-250/sf/p1-vs-p2"
        tour, surface = TournamentExtractor.determine_tournament_and_surface(
            url, ["Stockholm (ATP) - Hard Court"]
        )
        self.assertEqual(surface, "Hard")
        self.assertIn("Stockholm", tour)

if __name__ == "__main__":
    unittest.main()
