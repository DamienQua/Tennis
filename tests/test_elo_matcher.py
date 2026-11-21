import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from data_providers.elo_matcher import EloMatcher
from data_providers.elo_matcher import get_elo_index
from backtest.fast_elo_matcher import FastEloMatcher
from utils.player_identity import canonical_name, names_match


def test_all_surfaces_have_exact_columns_and_reuse_one_index():
    table = "Carlos Alcaraz 2150.5 2100.2 2180.4\nJannik Sinner 2200.1 2220.5 2100.0"
    get_elo_index.cache_clear()
    assert EloMatcher.find_elo_ratings(table, "Carlos Alcaraz", "Jannik Sinner", "Grass") == ("2180.4", "2100.0")
    assert EloMatcher.find_elo_ratings(table, "Carlos Alcaraz", "Jannik Sinner", "Clay") == ("2100.2", "2220.5")
    assert EloMatcher.find_elo_ratings(table, "Carlos Alcaraz", "Jannik Sinner", "Hard (Indoor)") == ("2150.5", "2200.1")
    assert get_elo_index.cache_info().misses == 1
    assert get_elo_index.cache_info().hits == 2
    assert get_elo_index(table) is get_elo_index(table)


def test_missing_columns_never_shift_or_default_to_another_surface():
    table = "João Sousa 1900 - 1700\nCoco Gauff 2000 1900 nan"
    assert EloMatcher.find_elo_ratings(table, "Joao Sousa", "Cori Gauff", "Clay") == ("", "")
    assert EloMatcher.find_elo_ratings(table, "Joao Sousa", "Cori Gauff", "Grass") == ("1700", "")
    assert EloMatcher.find_elo_ratings(table, "Joao Sousa", "Cori Gauff", "Unknown") == ("", "")
    assert EloMatcher.find_elo_ratings(table, "Joao Sousa", "Cori Gauff", "Hard/Clay") == ("", "")


def test_full_identity_aliases_accents_and_ambiguous_rows():
    assert names_match("João Sousa", "JOAO SOUSA")
    assert names_match("Cori Gauff", "Coco Gauff")
    assert names_match("Albert Ramos-Viñolas", "Albert Ramos")
    assert canonical_name("  Jean-René  Lisnard ") == "jean rene lisnard"
    assert not names_match("João Sousa", "Sousa")
    assert not names_match("Juan Manuel Cerundolo", "Francisco Cerundolo")
    assert not names_match("", "")
    table = "João Sousa 1900 1800 1700\nJoao Sousa 2000 1900 1800\nJoao Sousa 1900 1800 1700"
    assert EloMatcher.find_elo_ratings(table, "Joao Sousa", "", "Hard") == ("", "")


def test_fast_matcher_rejects_ambiguous_initials_without_fuzzy_fallback():
    table = (
        "João Sousa 1900 1800 1700\nJoao Silva 1800 1700 1600\n"
        "Juan Silva 2000 1900 1800\nCoco Gauff 2100 2000 1900\n"
        "Juan Manuel Cerundolo 1700 1800 1600\nFrancisco Cerundolo 1800 1900 1700"
    )
    matcher = FastEloMatcher(table)
    assert matcher.get_elo("Sousa J.", "Grass") == 1700
    assert matcher.get_elo("Silva J.", "Hard") == 1500
    assert matcher.get_elo("Juan Silva", "Hard") == 2000
    assert matcher.get_elo("Cori Gauff", "Hard") == 2100
    assert matcher.get_elo("Cerundolo J.M.", "Clay") == 1800
    assert matcher.get_elo("Cerundolo F.", "Clay") == 1900
    assert matcher.get_elo("Sousa", "Hard") == 1500
    assert matcher.get_elo("Joao Soussa", "Hard") == 1500

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
