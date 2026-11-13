"""Tests unitaires pour la base SQLite TennisDatabase, le ROI et l'export Excel."""

from core.database import TennisDatabase
from core.models import MatchAnalysisData, PlayerStats


def _sample_match() -> MatchAnalysisData:
    return MatchAnalysisData(
        match_url="https://tennisinsight.com/match/500/2026-atp-lyon/sf/fils-vs-humbert",
        tournament="Lyon ATP 250",
        surface="Clay",
        player_a=PlayerStats(name="Arthur Fils", model_odds=1.55, book_odds=1.85, elo=1941.2),
        player_b=PlayerStats(name="Ugo Humbert", model_odds=2.35, book_odds=2.00, elo=1700.8),
    )


def test_database_match_deduplication(tmp_path):
    """Vérifie l'insertion unique des matchs dans SQLite."""
    db = TennisDatabase(db_path=str(tmp_path / "test_matches.db"))
    daily_txt = str(tmp_path / "Matchs.txt")
    match = _sample_match()

    assert db.save_match(match, daily_file=daily_txt) is True
    assert db.save_match(match, daily_file=daily_txt) is False
    assert db.is_match_analyzed(match.match_url) is True


def test_database_bet_settlement_roi_and_excel(tmp_path):
    """Vérifie le règlement d'un pari, le calcul du ROI et l'export Excel."""
    db = TennisDatabase(db_path=str(tmp_path / "test_bets.db"))
    xlsx_path = str(tmp_path / "Paris_Alpha_5_Plus.xlsx")
    match = _sample_match()

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
    assert db.save_bet(match, alpha_res) is True
    assert db.save_bet(match, alpha_res) is False
    assert len(db.get_pending_bets()) == 1

    db.settle_bet(match.match_url, "Arthur Fils")
    roi = db.get_roi_summary()
    assert roi == {"settled": 1, "won": 1, "winrate": 100.0, "profit": 1.70, "roi": 85.0}
    assert db.export_bets_to_excel(filepath=xlsx_path) == xlsx_path