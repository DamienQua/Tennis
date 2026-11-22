"""Tests unitaires pour la génération de fiches Excel par match."""

import unittest
from core.models import MatchAnalysisData, PlayerStats
from strategy.generate_match_xlsx import _prepare_match_data


class TestGenerateXlsx(unittest.TestCase):
    """Unit tests for Excel match preview workbook generation."""

    def test_prepare_match_data_contains_alpha(self):
        match = MatchAnalysisData(
            match_url="https://tennisinsight.com/match/1/2026-rg/qf/alcaraz-vs-fognini",
            tournament="Roland Garros 2026",
            surface="Clay",
            player_a=PlayerStats(
                name="Carlos Alcaraz",
                ranking=2,
                model_odds=1.25,
                book_odds=1.50,
                elo=2150.0,
                win_pct_career=82.0,
                win_pct_career_surface=84.0,
            ),
            player_b=PlayerStats(
                name="Fabio Fognini",
                ranking=95,
                model_odds=4.50,
                book_odds=2.80,
                elo=1900.0,
                win_pct_career=54.0,
                win_pct_career_surface=58.0,
            ),
        )
        rows = _prepare_match_data(match)
        strategy_rows = [row for row in rows if "STRATÉGIE ALPHA 5+" in row[0]]
        self.assertEqual(len(strategy_rows), 1)
        self.assertEqual(strategy_rows[0][1], "PARI CONSEILLÉ")
        self.assertEqual(strategy_rows[0][2], "-")

    def test_prepare_match_data_no_bet(self):
        match = MatchAnalysisData(
            match_url="https://tennisinsight.com/match/2/2026-rg/r32/p1-vs-p2",
            tournament="Roland Garros 2026",
            surface="Clay",
            player_a=PlayerStats(
                name="Player 1",
                model_odds=1.80,
                book_odds=1.75,
                elo=1900.0,
                win_pct_career=60.0,
            ),
            player_b=PlayerStats(
                name="Player 2",
                model_odds=1.90,
                book_odds=1.95,
                elo=1880.0,
                win_pct_career=58.0,
            ),
        )
        rows = _prepare_match_data(match)
        strategy_rows = [row for row in rows if "STRATÉGIE ALPHA 5+" in row[0]]
        self.assertEqual(len(strategy_rows), 1)
        self.assertEqual(strategy_rows[0][1], "-")
        self.assertEqual(strategy_rows[0][2], "-")


if __name__ == "__main__":
    unittest.main()
