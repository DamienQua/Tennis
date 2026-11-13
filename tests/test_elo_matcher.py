import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from data_providers.elo_matcher import EloMatcher

class TestEloMatcher(unittest.TestCase):
    """Unit tests for Elo rating extraction and name matching."""
    def test_extract_elo_rating_clay(self):
        line = "Carlos Alcaraz 2150.5 2100.2 2180.4"
        rating = EloMatcher.extract_elo_rating(line, "Carlos Alcaraz", "Clay")
        self.assertTrue(bool(rating))

    def test_extract_elo_rating_hard(self):
        line = "Jannik Sinner 2200.1 2220.5 2100.0"
        rating = EloMatcher.extract_elo_rating(line, "Jannik Sinner", "Hard")
        self.assertTrue(bool(rating))

    def test_find_elo_ratings(self):
        elo_sample = (
            "Carlos Alcaraz 2150.5 2100.2 2180.4\n"
            "Jannik Sinner 2200.1 2220.5 2100.0\n"
        )
        elo_a, elo_b = EloMatcher.find_elo_ratings(
            elo_sample, "Carlos Alcaraz", "Jannik Sinner", "Clay"
        )
        self.assertTrue(bool(elo_a))
        self.assertTrue(bool(elo_b))

    def test_alias_matching_cori_gauff(self):
        elo_sample = "Coco Gauff 2081.8 2044.5 1891.9\n"
        elo_a, _ = EloMatcher.find_elo_ratings(elo_sample, "Cori Gauff", "Other Player", "Hard")
        self.assertEqual(elo_a, "2081.8")

if __name__ == "__main__":
    unittest.main()
