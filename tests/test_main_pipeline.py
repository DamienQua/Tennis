import os
import sys
import unittest
import importlib
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch, MagicMock, AsyncMock

import aiohttp
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from main import determine_elo_data, _get_credential, MatchProcessor
import main as pipeline
from core.database import TennisDatabase
from core.models import MatchAnalysisData, PlayerStats

analysis_module = importlib.import_module("core.analyze_match")

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

def _session_config():
    return pipeline.SessionConfig(
        header={}, connector=MagicMock(),
        rate_limit=MagicMock(acquire=AsyncMock()), timeout=MagicMock(),
    )


def _match_url():
    return f"https://example.invalid/match/123/atp-{datetime.now().year}/alpha-beta/"


def _match(url, *, complete):
    return MatchAnalysisData(
        match_url=url, tournament="Test Open", surface="Grass", market_status="prematch",
        player_a=PlayerStats(name="Player Alpha", elo=2100, model_odds=1.5, book_odds=1.7 if complete else 0),
        player_b=PlayerStats(name="Player Beta", elo=1900, model_odds=3.0, book_odds=2.4 if complete else 0),
    )


def _state(db, url):
    with db._session() as connection:
        return dict(connection.execute(
            "SELECT analysis_status, attempt_count FROM matches WHERE match_url = ?", (url,),
        ).fetchone())


@pytest.mark.asyncio
async def test_incomplete_analysis_is_retried_until_complete_across_runs(monkeypatch, tmp_path):
    url = _match_url()
    analyze = AsyncMock(side_effect=[_match(url, complete=False), None, _match(url, complete=True)])
    monkeypatch.setattr(pipeline, "analyze_match", analyze)
    session, config = MagicMock(), _session_config()
    db_path, dump_path = str(tmp_path / "pipeline.db"), str(tmp_path / "pipeline.sql")

    for expected_status, expected_attempt in [("incomplete", 1), ("retry", 2), ("complete", 3)]:
        # Chaque passage recharge l'état persistant comme une nouvelle exécution.
        db = TennisDatabase(db_path, dump_path)
        await pipeline.process_matches(session, config, [], [url], db=db)
        assert _state(db, url) == {"analysis_status": expected_status, "attempt_count": expected_attempt}
        assert db.is_match_analyzed(url) is (expected_status == "complete")

    db = TennisDatabase(db_path, dump_path)
    assert await pipeline.process_matches(session, config, [], [url], db=db) == ""
    assert analyze.await_count == 3
    assert _state(db, url)["attempt_count"] == 3


@pytest.mark.asyncio
async def test_duplicate_urls_in_one_batch_are_analyzed_only_once_even_when_incomplete(monkeypatch, tmp_path):
    url = _match_url()
    analyze = AsyncMock(return_value=_match(url, complete=False))
    monkeypatch.setattr(pipeline, "analyze_match", analyze)
    db = TennisDatabase(str(tmp_path / "pipeline.db"), str(tmp_path / "pipeline.sql"))
    output = await pipeline.process_matches(
        MagicMock(), _session_config(), [], [url, f" {url} ", url], db=db,
    )
    assert len(output.splitlines()) == 1
    analyze.assert_awaited_once()
    assert _state(db, url) == {"analysis_status": "incomplete", "attempt_count": 1}


@pytest.mark.asyncio
async def test_orchestrator_loads_surface_elo_before_computing_probabilities(monkeypatch):
    monkeypatch.setattr(analysis_module, "_fetch_match_soups", AsyncMock(return_value={
        "soup_main": None, "soup_overview": None,
    }))

    def populate(match, *args):
        match.surface = "Grass"
        match.player_a.name, match.player_b.name = "Player Alpha", "Player Beta"

    monkeypatch.setattr(analysis_module, "_populate_metadata", populate)
    find_elo = MagicMock(return_value=(2100, 1900))
    monkeypatch.setattr(analysis_module.EloMatcher, "find_elo_ratings", find_elo)
    monkeypatch.setattr(analysis_module, "_run_analysis_phases", AsyncMock())
    monkeypatch.setattr(analysis_module, "fetch_both_odds", AsyncMock(return_value={}))
    monkeypatch.setattr(analysis_module, "odds_match", AsyncMock())
    observed = []
    monkeypatch.setattr(analysis_module, "compare_players", lambda match: observed.append(
        (match.player_a.elo, match.player_b.elo),
    ))
    monkeypatch.setattr(analysis_module, "compare_indice", MagicMock())
    monkeypatch.setattr(analysis_module, "generate_match_xlsx", MagicMock())
    monkeypatch.setattr(analysis_module, "_evaluate_and_record_strategy", MagicMock())

    result = await analysis_module.analyze_match(MagicMock(), {}, _match_url(), [], "elo fixture")
    assert observed == [(2100.0, 1900.0)]
    assert result.player_a.elo == 2100
    find_elo.assert_called_once_with("elo fixture", "Player Alpha", "Player Beta", "Grass")


@pytest.fixture
def simulated_pipeline(monkeypatch):
    args = SimpleNamespace(update_results=False, no_email=False)
    monkeypatch.setattr(pipeline, "_parse_cli_args", lambda: args)
    monkeypatch.setattr(pipeline, "configure_logging", MagicMock())
    monkeypatch.setattr(pipeline, "create_session_config", _session_config)
    session_factory = MagicMock()
    session_factory.return_value.__aenter__.return_value = MagicMock()
    monkeypatch.setattr(pipeline.aiohttp, "ClientSession", session_factory)
    db = MagicMock()
    db.export_bets_to_excel.return_value = "tracking.xlsx"
    monkeypatch.setattr(pipeline, "TennisDatabase", lambda: db)
    monkeypatch.setattr(pipeline, "login", AsyncMock())
    monkeypatch.setattr(pipeline, "elo_table", AsyncMock(return_value="elo fixture"))
    monkeypatch.setattr(pipeline, "fetch_match_previews", AsyncMock(return_value=([], [_match_url()])))
    process = AsyncMock(return_value="match one\nmatch two\n")
    monkeypatch.setattr(pipeline, "process_matches", process)
    send = MagicMock(return_value=False)
    monkeypatch.setattr(pipeline, "send_daily_email", send)
    monkeypatch.setattr(pipeline, "get_session_bets", lambda: [])
    return SimpleNamespace(args=args, db=db, process=process, send=send)


@pytest.mark.asyncio
async def test_failed_email_is_reported_after_analysis_has_been_saved(simulated_pipeline):
    with pytest.raises(RuntimeError, match="Notification email échouée"):
        await pipeline.main()
    simulated_pipeline.db.export_sql_dump.assert_called_once()
    simulated_pipeline.db.export_bets_to_excel.assert_called_once()
    simulated_pipeline.send.assert_called_once_with([], total_matches=2, filepath="tracking.xlsx")


@pytest.mark.asyncio
async def test_analysis_failure_still_exports_database_and_does_not_send_email(simulated_pipeline):
    simulated_pipeline.process.side_effect = RuntimeError("analysis failed")
    with pytest.raises(RuntimeError, match="analysis failed"):
        await pipeline.main()
    simulated_pipeline.db.export_sql_dump.assert_called_once()
    simulated_pipeline.send.assert_not_called()


@pytest.mark.asyncio
async def test_no_email_option_skips_notification_without_losing_exports(simulated_pipeline):
    simulated_pipeline.args.no_email = True
    await pipeline.main()
    simulated_pipeline.db.export_sql_dump.assert_called_once()
    simulated_pipeline.db.export_bets_to_excel.assert_called_once()
    simulated_pipeline.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
