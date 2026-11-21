"""Tests unitaires pour la base SQLite TennisDatabase, CLV, dump SQL et ROI."""

import os
import sqlite3
import pytest
from unittest.mock import patch
from core.database import TennisDatabase
from core.models import MatchAnalysisData, PlayerStats


def _sample_match(url_suffix: str = "500") -> MatchAnalysisData:
    return MatchAnalysisData(
        match_url=f"https://tennisinsight.com/match/{url_suffix}/2026-atp-lyon/sf/fils-vs-humbert",
        tournament="Lyon ATP 250",
        surface="Clay",
        market_status="prematch",
        odds_observed_at="2026-01-01T10:00:00+00:00",
        scheduled_start="2026-01-01T12:00:00+00:00",
        player_a=PlayerStats(name="Arthur Fils", model_odds=1.55, book_odds=1.85, elo=1941.2),
        player_b=PlayerStats(name="Ugo Humbert", model_odds=2.35, book_odds=2.00, elo=1700.8),
    )


def test_database_match_deduplication_and_sql_dump(tmp_path):
    """Vérifie l'insertion unique, l'export en dump SQL texte et la restauration."""
    db_path = str(tmp_path / "test_matches.db")
    dump_path = str(tmp_path / "tennis_ai_dump.sql")
    daily_txt = str(tmp_path / "Matchs.txt")

    db = TennisDatabase(db_path=db_path, dump_path=dump_path)
    match = _sample_match()

    assert db.save_match(match, daily_file=daily_txt) is True
    assert db.save_match(match, daily_file=daily_txt) is False
    assert db.export_sql_dump() == dump_path

    # Suppression du .db binaire et reconstruction automatique depuis le dump SQL
    os.remove(db_path)
    db_restored = TennisDatabase(db_path=db_path, dump_path=dump_path)
    assert db_restored.is_match_analyzed(match.match_url) is True


def test_database_clv_void_and_roi(tmp_path):
    """Vérifie le calcul CLV, le remboursement sur forfait (w/o) et le bilan ROI."""
    db = TennisDatabase(db_path=str(tmp_path / "test_bets.db"))
    xlsx_path = str(tmp_path / "Paris_Alpha_5_Plus.xlsx")
    match_won = _sample_match("501")
    match_void = _sample_match("502")

    alpha_res = {
        "bet_recommended": True,
        "selected_player": "Arthur Fils",
        "book_odds": 1.85,
        "model_odds": 1.55,
        "model_prob": 0.58,
        "ev_percent": 7.3,
        "elo_diff": 240.4,
        "kelly_stake_pct": 2.0,
    }
    assert db.save_bet(match_won, alpha_res) is True
    assert db.save_bet(match_void, alpha_res) is True

    assert db.update_closing_odds(match_won.match_url, 1.70, "2026-01-01T11:00:00Z")
    db.settle_bet(match_won.match_url, "Arthur Fils", is_void=False)
    db.settle_bet(match_void.match_url, "Ugo Humbert", is_void=True)

    roi = db.get_roi_summary()
    assert roi == {
        "settled": 1,
        "won": 1,
        "winrate": 100.0,
        "profit": 1.70,
        "roi": 85.0,
        "avg_clv": 8.82,
        "clv_samples": 1,
    }
    assert db.export_bets_to_excel(filepath=xlsx_path) == xlsx_path


def _bet_result(match):
    return {
        "bet_recommended": True, "selected_player": match.player_a.name,
        "book_odds": 1.85, "model_odds": 1.55, "model_prob": 0.58,
        "ev_percent": 7.3, "elo_diff": 240.4, "kelly_stake_pct": 2.0,
    }


def test_incomplete_match_is_updated_on_retry_and_complete_match_is_preserved():
    db = TennisDatabase()
    match = _sample_match()
    match.player_a.book_odds = 0
    assert db.save_match(match)
    assert match.match_url not in db.load_reviewed_urls()
    assert not db.save_bet(match, _bet_result(match))
    db.record_retry(match.match_url, "HTTP indisponible")
    match.player_a.book_odds = 1.85
    assert db.save_match(match)
    assert db.is_match_analyzed(match.match_url)
    db.record_retry(match.match_url, "Ne doit pas écraser un succès")
    assert not db.save_match(match)
    with db._session() as conn:
        row = conn.execute("SELECT * FROM matches").fetchone()
    assert row["analysis_status"] == "complete"
    assert row["last_error"] == ""
    assert row["attempt_count"] == 3


@pytest.mark.parametrize("selected,winner,expected", [
    ("Coco Gauff", "Cori Gauff", "Gagné"),
    ("João Sousa", "Joao Sousa", "Gagné"),
    ("João Sousa", "Sousa", "En attente"),
    ("Arthur Fils", "Unknown Player", "En attente"),
    ("Arthur Fils", "Ugo Humbert", "Perdu"),
])
def test_settlement_requires_an_unambiguous_participant(selected, winner, expected):
    db = TennisDatabase()
    match = _sample_match()
    match.player_a.name = selected
    assert db.save_bet(match, _bet_result(match))
    assert db.settle_bet(match.match_url, winner) is (expected != "En attente")
    with db._session() as conn:
        row = conn.execute("SELECT * FROM bets").fetchone()
    assert row["status"] == expected
    if expected != "En attente":
        assert not db.settle_bet(match.match_url, "Ugo Humbert")


def test_closing_quote_requires_timestamp_and_cannot_move_backwards_or_into_live():
    db = TennisDatabase()
    match = _sample_match()
    assert db.save_bet(match, _bet_result(match))
    assert not db.update_closing_odds(match.match_url, 1.7)
    assert not db.update_closing_odds(match.match_url, float("nan"), "2026-01-01T11:00:00Z")
    assert not db.update_closing_odds(match.match_url, 1.7, "2026-01-01T11:00:00")
    assert db.update_closing_odds(match.match_url, 1.7, "2026-01-01T11:00:00Z")
    assert not db.update_closing_odds(match.match_url, 1.1, "2026-01-01T12:00:00Z")
    assert not db.update_closing_odds(match.match_url, 1.2, "2026-01-01T10:59:00Z")
    pending = db.get_pending_bets()[0]
    assert pending["closing_odds"] == 1.7
    assert db.settle_bet(match.match_url, match.player_a.name)
    assert not db.update_closing_odds(match.match_url, 1.5, "2026-01-01T11:59:00Z")


def test_missing_clv_is_not_reported_as_zero_or_as_the_purchase_price(tmp_path):
    import openpyxl

    db = TennisDatabase()
    match = _sample_match()
    db.save_bet(match, _bet_result(match))
    db.settle_bet(match.match_url, "Arthur Fils")
    summary = db.get_roi_summary()
    assert summary["avg_clv"] is None
    assert summary["clv_samples"] == 0
    path = db.export_bets_to_excel(str(tmp_path / "export.xlsx"))
    workbook = openpyxl.load_workbook(path)
    assert workbook.active.cell(2, 8).value is None
    assert workbook.active.cell(2, 9).value == "Indisponible"
    workbook.close()


def test_clv_cannot_replace_the_initial_match_with_a_future_rematch():
    db = TennisDatabase()
    match = _sample_match()
    db.save_bet(match, _bet_result(match))
    assert not db.update_closing_odds(
        match.match_url, 1.1, "2026-01-08T11:00:00Z", "2026-01-08T12:00:00Z"
    )
    pending = db.get_pending_bets()[0]
    assert pending["scheduled_start"] == match.scheduled_start
    assert pending["closing_odds"] is None
    assert db.update_closing_odds(
        match.match_url, 1.7, "2026-01-01T11:00:00Z", "2026-01-01T13:00:00+01:00"
    )


def test_clv_stays_unavailable_if_original_match_has_no_start_time():
    db = TennisDatabase()
    match = _sample_match()
    match.scheduled_start = ""
    db.save_bet(match, _bet_result(match))
    assert not db.update_closing_odds(
        match.match_url, 1.1, "2026-01-08T11:00:00Z", "2026-01-08T12:00:00Z"
    )


def test_failed_dump_replacement_preserves_the_previous_backup(tmp_path):
    db = TennisDatabase()
    target = tmp_path / "backup.sql"
    target.write_text("previous valid backup", encoding="utf-8")
    with patch("core.database.os.replace", side_effect=OSError("disk error")):
        with pytest.raises(OSError):
            db.export_sql_dump(str(target))
    assert target.read_text(encoding="utf-8") == "previous valid backup"
    assert not list(tmp_path.glob(".tennis-dump-*"))


def test_old_schema_migration_preserves_history_and_recovers_incomplete_matches(tmp_path):
    path = str(tmp_path / "legacy.db")
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE matches (
            match_url TEXT PRIMARY KEY, analyzed_at TEXT NOT NULL, tournament TEXT, surface TEXT,
            player_a TEXT, player_b TEXT, model_odds_a REAL, model_odds_b REAL,
            book_odds_a REAL, book_odds_b REAL, elo_a REAL, elo_b REAL,
            confidence_index REAL, summary_line TEXT)""")
        for url, odds in (("complete", 1.8), ("incomplete", 0.0)):
            conn.execute("INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (url, "2026-01-01", "Tour", "Clay", "Alpha", "Beta", 1.7, 2.4,
                          odds, 2.1, 1900, 1700, 1, "original summary"))
    db = TennisDatabase(db_path=path)
    assert db.load_reviewed_urls() == {"complete"}
    with db._session() as conn:
        assert conn.execute("SELECT count(*) FROM matches").fetchone()[0] == 2
        assert conn.execute("SELECT summary_line FROM matches WHERE match_url='complete'").fetchone()[0] == "original summary"
    assert TennisDatabase(db_path=path).load_reviewed_urls() == {"complete"}
