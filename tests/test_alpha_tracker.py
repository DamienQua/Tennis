import unittest
import os
import sys
import tempfile
import openpyxl

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from strategy.alpha_tracker import record_alpha_selection, HEADERS

class TestAlphaTracker(unittest.TestCase):
    """Unit tests for Alpha strategy selection workbook recording."""
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "test_tracker.xlsx")

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    def test_record_selection_success(self):
        alpha_res = {
            "bet_recommended": True,
            "selected_player": "Carlos Alcaraz",
            "book_odds": 1.65,
            "model_odds": 1.25,
            "model_prob": 0.78,
            "ev_percent": 8.5,
            "elo_diff": 195.0
        }

        success = record_alpha_selection(
            tournament="Roland Garros",
            surface="Clay",
            player1="Carlos Alcaraz",
            player2="Fabio Fognini",
            alpha_res=alpha_res,
            match_url="https://tennisinsight.com/match/123/alcaraz-vs-fognini",
            filepath=self.test_file
        )

        self.assertTrue(success)
        self.assertTrue(os.path.exists(self.test_file))

        workbook = openpyxl.load_workbook(self.test_file)
        sheet = workbook.active
        self.assertEqual(sheet.max_row, 2)
        self.assertEqual(sheet.cell(row=1, column=1).value, HEADERS[0])
        self.assertEqual(sheet.cell(row=2, column=2).value, "Roland Garros")
        self.assertEqual(sheet.cell(row=2, column=6).value, "Carlos Alcaraz")
        self.assertEqual(sheet.cell(row=2, column=7).value, 1.65)
        self.assertEqual(sheet.cell(row=2, column=12).value, "En attente")

    def test_record_selection_ignored_when_no_bet(self):
        alpha_res = {"bet_recommended": False}
        success = record_alpha_selection(
            tournament="Wimbledon",
            surface="Grass",
            player1="P1",
            player2="P2",
            alpha_res=alpha_res,
            filepath=self.test_file
        )
        self.assertFalse(success)
        self.assertFalse(os.path.exists(self.test_file))

    def test_record_selection_deduplication(self):
        alpha_res = {
            "bet_recommended": True,
            "selected_player": "Jannik Sinner",
            "book_odds": 1.50,
            "model_odds": 1.20,
            "model_prob": 0.80,
            "ev_percent": 12.0,
            "elo_diff": 210.0
        }

        # First record
        first = record_alpha_selection(
            tournament="Australian Open",
            surface="Hard",
            player1="Jannik Sinner",
            player2="Daniil Medvedev",
            alpha_res=alpha_res,
            match_url="https://tennisinsight.com/match/456/sinner-vs-medvedev",
            filepath=self.test_file
        )
        self.assertTrue(first)

        # Duplicate attempt with same URL and players
        second = record_alpha_selection(
            tournament="Australian Open",
            surface="Hard",
            player1="Jannik Sinner",
            player2="Daniil Medvedev",
            alpha_res=alpha_res,
            match_url="https://tennisinsight.com/match/456/sinner-vs-medvedev",
            filepath=self.test_file
        )
        self.assertFalse(second)

        workbook = openpyxl.load_workbook(self.test_file)
        sheet = workbook.active
        self.assertEqual(sheet.max_row, 2)

if __name__ == "__main__":
    unittest.main()
