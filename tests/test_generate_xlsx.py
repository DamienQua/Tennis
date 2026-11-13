import unittest
import numpy as np
import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from strategy.generate_match_xlsx import generate_match_xlsx, _prepare_match_data

class TestGenerateXlsx(unittest.TestCase):
    """Unit tests for Excel match preview workbook generation."""
    def test_prepare_match_data_contains_alpha(self):
        match_vec = np.full(44, '', dtype='<U100')
        match_vec[0] = 'Roland Garros 2026'
        match_vec[1] = 'Clay'
        match_vec[2] = 'Carlos Alcaraz'
        match_vec[3] = 'Fabio Fognini'
        match_vec[4] = '2'
        match_vec[5] = '95'
        match_vec[36] = '1.25'
        match_vec[37] = '4.50'
        match_vec[38] = '1.50'
        match_vec[39] = '2.80'
        match_vec[40] = '2150'
        match_vec[41] = '1900'

        rows = _prepare_match_data(match_vec, match_vec[2], match_vec[3])
        # Find row with STRATÉGIE ALPHA 5+
        strategy_rows = [row for row in rows if 'STRATÉGIE ALPHA 5+' in row[0]]
        self.assertEqual(len(strategy_rows), 1)
        self.assertEqual(strategy_rows[0][1], 'PARI CONSEILLÉ')
        self.assertEqual(strategy_rows[0][2], '-')

    def test_prepare_match_data_no_bet(self):
        match_vec = np.full(44, '', dtype='<U100')
        match_vec[0] = 'Roland Garros 2026'
        match_vec[2] = 'Player 1'
        match_vec[3] = 'Player 2'
        match_vec[36] = '1.80'
        match_vec[37] = '1.90'
        match_vec[38] = '1.75'
        match_vec[39] = '1.95'
        match_vec[40] = '1900'
        match_vec[41] = '1880'

        rows = _prepare_match_data(match_vec, match_vec[2], match_vec[3])
        strategy_rows = [row for row in rows if 'STRATÉGIE ALPHA 5+' in row[0]]
        self.assertEqual(len(strategy_rows), 1)
        self.assertEqual(strategy_rows[0][1], '-')
        self.assertEqual(strategy_rows[0][2], '-')

if __name__ == '__main__':
    unittest.main()
