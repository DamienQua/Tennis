import os
import sys
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

import aiohttp

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from main import determine_elo_data, _get_credential, MatchProcessor

class TestMainPipeline(unittest.TestCase):
    """Unit tests for pipeline configuration, elo data selection, and formatting."""
    def test_determine_elo_data(self):
        wta = "wta_table"
        atp = "atp_table"
        elo_wta = determine_elo_data("https://.../wta-tour/...", atp, wta)
        self.assertTrue(elo_wta.startswith("wta_table"))

        elo_atp = determine_elo_data("https://.../atp-tour/...", atp, wta)
        self.assertTrue(elo_atp.startswith("atp_table"))

    def test_get_credential_prefers_os_environ(self):
        with patch.dict(os.environ, {"TEST_KEY": "env_val"}):
            val = _get_credential({"TEST_KEY": "file_val"}, "TEST_KEY")
            self.assertEqual(val, "env_val")

    def test_get_credential_fallback_to_file(self):
        env_copy = os.environ.copy()
        env_copy.pop("TEST_KEY", None)
        with patch.dict(os.environ, env_copy, clear=True):
            val = _get_credential({"TEST_KEY": "file_val"}, "TEST_KEY")
            self.assertEqual(val, "file_val")

    def test_finalize_result_format(self):
        session = MagicMock()
        processor = MatchProcessor(session, {}, MagicMock(), "")
        res = processor.finalize_result("Tournament, Clay, P1, P2", "http://test", 100.0)
        self.assertIn("Tournament, Clay, P1, P2", res)
        self.assertIn("http://test", res)

if __name__ == "__main__":
    unittest.main()
