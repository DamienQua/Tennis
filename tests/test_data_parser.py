import unittest
import sys
import os

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
        self.assertEqual(val_na, 0.0)

    def test_parse_win_percentages_empty(self):
        result = TennisDataParser.parse_win_percentages(None)
        self.assertEqual(result, [])

    def test_parse_win_percentages_with_text(self):
        raw = "Header Matches 50% Matches 65% (12 months) 70% (since 2000) 60%"
        result = TennisDataParser.parse_win_percentages(DummySoup(raw))
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) >= 2)

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
