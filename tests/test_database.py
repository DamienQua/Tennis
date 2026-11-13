"""Tests unitaires pour la base SQLite TennisDatabase, CLV, dump SQL et ROI."""

import os
from core.database import TennisDatabase
from core.models import MatchAnalysisData, PlayerStats


def _sample_match(url_suffix: str = "500") -> MatchAnalysisData:
    return MatchAnalysisData(
        match_url=f"https://tennisinsight.com/match/{url_suffix}/2026-atp-lyon/sf/fils-vs-humbert",
        tournament="Lyon ATP 250",
        surface="Clay",
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

    db.update_closing_odds(match_won.match_url, 1.70)
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
    }
    assert db.export_bets_to_excel(filepath=xlsx_path) == xlsx_path