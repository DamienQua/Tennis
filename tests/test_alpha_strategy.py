import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from strategy.alpha_strategy import evaluate_alpha_strategy, format_alpha_summary
from backtest.strategy_evaluator import StrategyEvaluator

class TestAlphaStrategy(unittest.TestCase):
    """Unit tests for the Alpha 5+ value betting strategy."""
    def test_alpha_strategy_bet_j1(self):
        # J1 model: 1.25, J2 model: 4.50 -> p1 ~ 78.3%
        # Book odds: 1.50 -> EV = 0.783 * 1.50 - 1 = +17.4% (> 3%)
        # Elo: J1: 2100, J2: 1900 -> diff = +200 (>= 150)
        # Book odds 1.50 in [1.40, 2.50]
        res = evaluate_alpha_strategy(
            model_1=1.25, model_2=4.50,
            book_1=1.50, book_2=2.80,
            elo_1=2100, elo_2=1900,
            player_1="Carlos Alcaraz", player_2="Fabio Fognini"
        )
        self.assertTrue(res["bet_recommended"])
        self.assertEqual(res["selected_player"], "Carlos Alcaraz")
        self.assertEqual(res["player_index"], 1)
        self.assertEqual(res["signal_j1"], "PARI CONSEILLÉ")
        self.assertEqual(res["signal_j2"], "-")
        self.assertGreater(res["ev_percent"], 3.0)
        self.assertGreaterEqual(res["elo_diff"], 150)
        self.assertIn("Carlos Alcaraz", res["summary"])

    def test_alpha_strategy_bet_j2(self):
        # J2 favored by model, odds 1.65 in [1.40, 2.50], Elo gap +180
        res = evaluate_alpha_strategy(
            model_1=3.50, model_2=1.35,
            book_1=3.00, book_2=1.65,
            elo_1=1750, elo_2=1950,
            player_1="Joueur A", player_2="Joueur B"
        )
        self.assertTrue(res["bet_recommended"])
        self.assertEqual(res["selected_player"], "Joueur B")
        self.assertEqual(res["player_index"], 2)
        self.assertEqual(res["signal_j1"], "-")
        self.assertEqual(res["signal_j2"], "PARI CONSEILLÉ")

    def test_no_bet_low_elo_gap(self):
        # Elo diff is only 80 (< 150)
        res = evaluate_alpha_strategy(
            model_1=1.30, model_2=3.80,
            book_1=1.55, book_2=2.60,
            elo_1=1980, elo_2=1900,
            player_1="P1", player_2="P2"
        )
        self.assertFalse(res["bet_recommended"])
        self.assertEqual(res["signal_j1"], "-")
        self.assertEqual(res["signal_j2"], "-")

    def test_no_bet_odds_out_of_range(self):
        # Book odds 1.30 is below minimum 1.40
        res_low = evaluate_alpha_strategy(
            model_1=1.15, model_2=5.00,
            book_1=1.30, book_2=4.00,
            elo_1=2150, elo_2=1800
        )
        self.assertFalse(res_low["bet_recommended"])

        # Book odds 2.65 is above maximum 2.50
        res_high = evaluate_alpha_strategy(
            model_1=1.50, model_2=2.50,
            book_1=2.65, book_2=1.45,
            elo_1=2150, elo_2=1800
        )
        self.assertFalse(res_high["bet_recommended"])

    def test_no_bet_low_ev(self):
        # Book odds 1.40 but model odds 1.45 -> EV < 3%
        res = evaluate_alpha_strategy(
            model_1=1.45, model_2=2.80,
            book_1=1.40, book_2=2.90,
            elo_1=2100, elo_2=1800
        )
        self.assertFalse(res["bet_recommended"])

    def test_missing_or_invalid_data(self):
        # Empty strings or zero values
        res = evaluate_alpha_strategy("", "", "", "", "", "")
        self.assertFalse(res["bet_recommended"])
        self.assertEqual(res["signal_j1"], "Données incomplètes")
        self.assertEqual(res["signal_j2"], "Données incomplètes")

    def test_strategy_evaluator_wrapper(self):
        res = StrategyEvaluator.evaluate_alpha_5_plus(
            model_1=1.25, model_2=4.50,
            book_1=1.50, book_2=2.80,
            elo_1=2100, elo_2=1900,
            player_1="J1", player_2="J2"
        )
        self.assertTrue(res["bet_recommended"])
        self.assertEqual(res["selected_player"], "J1")

if __name__ == "__main__":
    unittest.main()
