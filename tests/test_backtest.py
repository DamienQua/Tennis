import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backtest.historical_odds import HistoricalOddsProvider
from backtest.strategy_evaluator import StrategyEvaluator
from backtest.backtest_engine import BacktestEngine
from backtest.fast_elo_matcher import FastEloMatcher
from backtest.point_in_time_stats import PointInTimeStats
from backtest.point_in_time_backtest import PointInTimeBacktester, PointInTimeBacktest

class TestBacktest(unittest.TestCase):
    """Unit tests for historical odds lookup and backtest strategy evaluation."""
    def test_historical_odds_matching(self):
        provider = HistoricalOddsProvider()
        match = provider.get_match_odds("Novak Djokovic", "Daniil Medvedev", 2023, "atp")
        self.assertIsNotNone(match)
        self.assertEqual(match["winner"], "Novak Djokovic")
        self.assertGreater(match["odds_a"]["b365"], 1.0)

    def test_strategy_evaluator_confluence(self):
        evaluator = StrategyEvaluator()
        # Case OK J1: Excel 1.40 < 2.50, Book 1.60 < 2.30, ELO 2000 > 1800,
        # Surf 70 > 60, Book 1.60 > Excel 1.40
        status = evaluator.evaluate_confluence(
            1.40, 2.50, 1.60, 2.30, 2000.0, 1800.0, 70.0, 60.0
        )
        self.assertEqual(status, "OK J1")

        bet = evaluator.evaluate_match_confluence(
            "Alcaraz", "Ruud", "Madrid",
            1.40, 2.50, 1.60, 2.30, 2000.0, 1800.0, 70.0, 60.0, "Alcaraz"
        )
        self.assertIsNotNone(bet)
        self.assertTrue(bet.won)
        self.assertEqual(bet.bet_on, "Alcaraz")

        # Case PAS OK: Book J1 (1.30) < Excel J1 (1.40) -> No value!
        status_no_val = evaluator.evaluate_confluence(
            1.40, 2.50, 1.30, 2.80, 2000.0, 1800.0, 70.0, 60.0
        )
        self.assertEqual(status_no_val, "PAS OK")

    def test_backtest_engine(self):
        engine = BacktestEngine(output_dir="backtest/results_test")
        res = engine.process_match_result(
            "url_test",
            "Novak Djokovic",
            "Daniil Medvedev",
            "Adelaide",
            1.40,
            3.00,
            elo_a=2100.0,
            elo_b=2000.0,
            surface_a=75.0,
            surface_b=70.0,
            year=2023,
            gender="atp"
        )
        self.assertIsNotNone(res)
        summary = engine.evaluator.get_summary()
        self.assertIn("total_bets", summary)

    def test_fast_elo_matcher(self):
        sample_elo = (
            "Novak Djokovic 2150.0 2050.0 2100.0\n"
            "Carlos Alcaraz 2000.0 2100.0 1950.0\n"
        )
        matcher = FastEloMatcher(sample_elo)
        self.assertEqual(matcher.get_elo("Djokovic N.", "Hard"), 2150.0)
        self.assertEqual(matcher.get_elo("Djokovic N.", "Clay"), 2050.0)
        self.assertEqual(matcher.get_elo("Djokovic N.", "Grass"), 2100.0)
        self.assertEqual(matcher.get_elo("Alcaraz C.", "Clay"), 2100.0)
        # Fuzzy match test
        self.assertEqual(matcher.get_elo("Novak Djokovic", "Hard"), 2150.0)
        # Unknown player fallback
        self.assertEqual(matcher.get_elo("Unknown Player", "Hard"), 1500.0)

    def test_point_in_time_stats(self):
        import pandas as pd
        matches = pd.DataFrame([
            {"Date": "2023-01-10", "Winner": "Player A", "Loser": "Player B", "Surface": "Hard"},
            {"Date": "2023-02-15", "Winner": "Player A", "Loser": "Player C", "Surface": "Clay"},
            {"Date": "2023-03-20", "Winner": "Player B", "Loser": "Player A", "Surface": "Hard"},
        ])
        stats = PointInTimeStats(matches)
        # Before 2023-03-01: Player A has 2 wins in 2 matches (100%), 1 hard (100%), 1 clay (100%)
        p_12m, p_surf, total = stats.get_player_stats_before(
            "Player A", pd.Timestamp("2023-03-01"), "Hard"
        )
        self.assertEqual(p_12m, 100.0)
        self.assertEqual(p_surf, 100.0)
        self.assertEqual(total, 2)

        # After 2023-03-20: Player A has 2 wins in 3 matches (66.67%), 1 win in 2 hard matches (50%)
        p_12m_post, p_surf_post, total_post = stats.get_player_stats_before(
            "Player A", pd.Timestamp("2023-04-01"), "Hard"
        )
        self.assertEqual(p_12m_post, 66.67)
        self.assertEqual(p_surf_post, 50.0)
        self.assertEqual(total_post, 3)

        # Player with no matches
        p_12m_unk, p_surf_unk, total_unk = stats.get_player_stats_before(
            "Unknown", pd.Timestamp("2023-04-01"), "Hard"
        )
        self.assertEqual(p_12m_unk, 50.0)
        self.assertEqual(p_surf_unk, 50.0)
        self.assertEqual(total_unk, 0)

    def test_point_in_time_backtester_alias(self):
        self.assertIs(PointInTimeBacktester, PointInTimeBacktest)

if __name__ == "__main__":
    unittest.main()
