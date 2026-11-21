"""Les cotes sont arrondies dans les exports, sans modifier les calculs ni SQLite."""

from dataclasses import asdict

import openpyxl
import pytest

from core.database import TennisDatabase
from core.models import MatchAnalysisData, PlayerStats
from strategy.alpha_strategy import evaluate_alpha_strategy
from strategy.generate_match_xlsx import generate_match_xlsx


@pytest.fixture
def precise_match():
    return MatchAnalysisData(
        match_url="https://tennisinsight.com/match/formatting-test/",
        tournament="Turin ATP WTF 2026",
        market_status="prematch",
        odds_observed_at="2026-11-21T10:00:00+00:00",
        scheduled_start="2026-11-21T18:00:00+00:00",
        player_a=PlayerStats(
            name="Alexander Zverev", elo=2200.123,
            model_odds=1.736842105263158, book_odds=1.834567,
        ),
        player_b=PlayerStats(
            name="Carlos Alcaraz", elo=2000.456,
            model_odds=2.375971631205674, book_odds=2.201234,
        ),
    )


def test_summary_odds_have_two_decimals_without_rounding_other_fields(precise_match):
    before = asdict(precise_match)
    fields = precise_match.to_summary_line().split(", ")

    assert fields[4:8] == ["1.74", "2.38", "1.83", "2.20"]
    assert fields[8:10] == ["2200.123", "2000.456"]
    assert asdict(precise_match) == before


def test_missing_odds_stay_empty_in_summary_and_workbook():
    match = MatchAnalysisData(match_url="", tournament="Missing odds")
    assert match.to_summary_line().split(", ")[4:8] == ["", "", "", ""]

    path = generate_match_xlsx(match)
    workbook = openpyxl.load_workbook(path)
    try:
        for row in workbook.active.iter_rows():
            if row[0].value in {"Côte estimée", "Cote Bookmaker"}:
                assert all(cell.value is None for cell in row[1:])
    finally:
        workbook.close()


def test_match_workbook_contains_numeric_rounded_odds_and_preserves_strategy(precise_match):
    before = asdict(precise_match)
    alpha_before = evaluate_alpha_strategy(precise_match)
    assert alpha_before["bet_recommended"]
    pa, pb = precise_match.player_a, precise_match.player_b
    expected_probability = pb.model_odds / (pa.model_odds + pb.model_odds)
    assert alpha_before["ev"] == pytest.approx(expected_probability * pa.book_odds - 1)

    path = generate_match_xlsx(precise_match)
    workbook = openpyxl.load_workbook(path)
    try:
        rows = {row[0].value: row[1:] for row in workbook.active.iter_rows()}
        for label, expected in (
            ("Côte estimée", [1.74, 2.38]),
            ("Cote Bookmaker", [1.83, 2.20]),
        ):
            assert [cell.value for cell in rows[label]] == expected
            assert all(cell.data_type == "n" for cell in rows[label])
            assert all(cell.number_format == "0.00" for cell in rows[label])
        assert [cell.value for cell in rows["Classement ELO"]] == [2200.123, 2000.456]
    finally:
        workbook.close()

    assert asdict(precise_match) == before
    assert evaluate_alpha_strategy(precise_match) == alpha_before


@pytest.mark.parametrize("with_closing", [False, True])
def test_tracking_export_rounds_odds_but_keeps_database_precision(precise_match, tmp_path, with_closing):
    db = TennisDatabase(db_path=str(tmp_path / "formatting.db"), dump_path=str(tmp_path / "formatting.sql"))
    alpha = evaluate_alpha_strategy(precise_match)
    assert db.save_bet(precise_match, alpha)
    if with_closing:
        assert db.update_closing_odds(precise_match.match_url, 1.712345, "2026-11-21T17:00:00Z")
    stored_before = db.get_pending_bets()[0]

    path = db.export_bets_to_excel(str(tmp_path / "tracking.xlsx"))
    workbook = openpyxl.load_workbook(path)
    try:
        for column, expected in ((7, 1.83), (8, 1.71 if with_closing else None), (10, 1.74)):
            cell = workbook.active.cell(2, column)
            assert cell.value == expected
            assert cell.number_format == "0.00"
            if expected is not None:
                assert cell.data_type == "n"
    finally:
        workbook.close()

    stored_after = db.get_pending_bets()[0]
    assert stored_after == stored_before
    assert stored_after["book_odds"] == precise_match.player_a.book_odds
    assert stored_after["model_odds"] == precise_match.player_a.model_odds
    if with_closing:
        assert stored_after["closing_odds"] == 1.712345
