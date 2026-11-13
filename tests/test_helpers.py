import unittest
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from utils.helpers import DateHelper

class DummyElement:
    """Mock HTML element for DateHelper tests."""
    def __init__(self, text):
        self.text = text

class TestDateHelper(unittest.TestCase):
    """Unit tests for DateHelper utility calculations."""
    def test_calculate_matches_last_month_empty(self):
        result = DateHelper.calculate_matches_last_month([], 1700000000)
        self.assertEqual(result, 0)

    def test_is_within_last_month(self):
        # 10 days ago
        now = datetime(2026, 11, 10).timestamp()
        elems = [DummyElement("Header"), DummyElement("Nov 01 2026")]
        within = DateHelper.is_within_last_month(elems, 1, now, one_month=2629800)
        self.assertTrue(within)

        # 60 days ago
        elems_old = [DummyElement("Header"), DummyElement("Sep 01 2026")]
        within_old = DateHelper.is_within_last_month(elems_old, 1, now, one_month=2629800)
        self.assertFalse(within_old)

if __name__ == "__main__":
    unittest.main()
