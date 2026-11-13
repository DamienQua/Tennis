import unittest
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.match_filter import MatchFilter

class TestMatchFilter(unittest.TestCase):
    """Unit tests for match URL filtering, year validation, and exclusions."""
    def setUp(self):
        self.year = str(datetime.now().year)

    def test_should_process_valid_wta(self):
        url = (
            f"https://tennisinsight.com/match/123/{self.year}-sopo-wta-ch/r32/"
            "player-a-vs-player-b"
        )
        self.assertTrue(MatchFilter.should_process(url))

    def test_should_process_already_reviewed(self):
        url = (
            f"https://tennisinsight.com/match/123/{self.year}-sopo-wta-ch/r32/"
            "player-a-vs-player-b"
        )
        self.assertFalse(MatchFilter.should_process(url, already_processed=url))

    def test_should_process_excluded_qualifiers(self):
        url = f"https://tennisinsight.com/match/123/{self.year}-sopo-wta-ch/q/player-a-vs-player-b"
        self.assertFalse(MatchFilter.should_process(url))

    def test_should_process_special_player_case(self):
        url = "https://tennisinsight.com/match/123/2020-itf-event/r32/andreeva-vs-other"
        self.assertTrue(MatchFilter.should_process(url))

if __name__ == "__main__":
    unittest.main()
