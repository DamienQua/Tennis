"""Règlement prudent des résultats et conservation exclusive des cotes avant match."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from strategy import result_settler


def _header(text):
    return f'<div class="match-preview-header">{text}</div>'


@pytest.mark.parametrize(
    "display,player_a,player_b,winner",
    [
        ("João Sousa def. Player Beta 6-3 6-2", "João Sousa", "Player Beta", "João Sousa"),
        ("Joao Sousa defeated Player Beta 6-3 6-2", "João Sousa", "Player Beta", "João Sousa"),
        ("Cori Gauff def. Player Beta 6-3 6-2", "Coco Gauff", "Player Beta", "Coco Gauff"),
        ("Final Player Beta def. João Sousa 6-3 6-2", "João Sousa", "Player Beta", "Player Beta"),
    ],
)
def test_winner_is_resolved_to_a_known_player(display, player_a, player_b, winner):
    assert result_settler._parse_match_outcome(_header(display), player_a, player_b) == (winner, False)


@pytest.mark.parametrize(
    "display,player_a,player_b",
    [
        ("J. Sousa def. Player Beta 6-3 6-2", "João Sousa", "Player Beta"),
        ("Sousa def. Player Beta 6-3 6-2", "João Sousa", "Player Beta"),
        ("Unknown Player def. Player Beta 6-3 6-2", "João Sousa", "Player Beta"),
        ("João Sousa def. Unknown Player 6-3 6-2", "João Sousa", "Player Beta"),
        ("Joao Sousa def. Player Beta 6-3 6-2", "João Sousa", "Joao Sousa"),
        ("João Sousa vs Player Beta Live 6-3 2-1", "João Sousa", "Player Beta"),
        ("João Sousa def. Player Beta retired", "João Sousa", "Player Beta"),
        ("Unknown João Sousa def. Player Beta 6-3 6-2", "João Sousa", "Player Beta"),
        ("João Sousa def. Player Beta Junior 6-3 6-2", "João Sousa", "Player Beta"),
        ("Unknown Player w/o Player Beta", "João Sousa", "Player Beta"),
        ("João Sousa vs Player Beta Junior 3-2 ret.", "João Sousa", "Player Beta"),
    ],
)
def test_uncertain_results_are_not_settled(display, player_a, player_b):
    assert result_settler._parse_match_outcome(_header(display), player_a, player_b) == (None, False)


@pytest.mark.parametrize("display", [
    "Player Alpha w/o Player Beta",
    "Player Alpha walkover Player Beta",
    "Player Alpha vs Player Beta 3-2 ret.",
    "Player Alpha vs Player Beta 0–0 retired",
])
def test_void_does_not_require_a_winner(display):
    assert result_settler._parse_match_outcome(_header(display), "Player Alpha", "Player Beta") == (None, True)


def test_retirement_after_a_completed_set_is_settled_normally():
    html = _header("Player Alpha def. Player Beta 7–6 1-0 retired")
    assert result_settler._parse_match_outcome(html, "Player Alpha", "Player Beta") == ("Player Alpha", False)


def test_historical_results_cannot_settle_a_current_match():
    html = (
        '<h1>Player Alpha vs Player Beta</h1>'
        '<div class="h2h-matches">Player Beta def. Player Alpha 6-0 6-0</div>'
        '<footer>Player Alpha def. Player Beta 6-3 6-2</footer>'
    )
    assert result_settler._parse_match_outcome(html, "Player Alpha", "Player Beta") == (None, False)
    assert result_settler._parse_match_outcome("Player Alpha def. Player Beta 6-0 6-0", "Player Alpha", "Player Beta") == (None, False)


def test_other_match_inside_the_same_page_container_cannot_void_the_bet():
    html = (
        '<main><h1>Player Alpha vs Player Beta</h1>'
        '<aside>Another Player w/o Someone Else</aside></main>'
    )
    assert result_settler._parse_match_outcome(html, "Player Alpha", "Player Beta") == (None, False)


@pytest.fixture
def bet():
    return {
        "match_url": "https://example.invalid/match/1", "player_a": "João Sousa",
        "player_b": "Player Beta", "selected_player": "João Sousa",
    }


def _mock_request(monkeypatch, html):
    response = Mock(status=200)
    response.text = AsyncMock(return_value=html)

    @asynccontextmanager
    async def request(session, method, url):
        assert method == "GET"
        yield response

    monkeypatch.setattr(result_settler, "request", request)


@pytest.mark.asyncio
async def test_void_is_recorded_without_a_winner(monkeypatch, bet):
    _mock_request(monkeypatch, _header("João Sousa w/o Player Beta"))
    db = Mock()
    db.settle_bet.return_value = True
    assert await result_settler._check_single_bet(Mock(), db, bet) is True
    db.settle_bet.assert_called_once_with(bet["match_url"], "", is_void=True)


@pytest.mark.asyncio
async def test_database_rejection_does_not_count_as_a_settlement(monkeypatch, bet):
    _mock_request(monkeypatch, _header("Joao Sousa def. Player Beta 6-3 6-2"))
    db = Mock()
    db.settle_bet.return_value = False
    assert await result_settler._check_single_bet(Mock(), db, bet) is False


@pytest.mark.asyncio
async def test_unknown_winner_never_becomes_a_loss(monkeypatch, bet):
    _mock_request(monkeypatch, _header("Unknown Player def. Player Beta 6-3 6-2"))
    monkeypatch.setattr(result_settler, "_refresh_clv_for_pending", AsyncMock())
    db = Mock()
    assert await result_settler._check_single_bet(Mock(), db, bet) is False
    db.settle_bet.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,observation,starts", [
    ("live", "valid", "future"),
    ("unknown", "valid", "future"),
    ("prematch", "missing", "future"),
    ("prematch", "naive", "future"),
    ("prematch", "valid", "missing"),
    ("prematch", "valid", "past"),
    ("prematch", "future", "future"),
])
async def test_clv_rejects_unproven_prematch_quotes(monkeypatch, bet, status, observation, starts):
    now = datetime.now(timezone.utc)

    async def odds(match, session):
        match.player_a.book_odds = 1.1
        match.market_status = status
        match.odds_observed_at = {
            "valid": (now - timedelta(seconds=1)).isoformat(), "missing": "",
            "naive": now.replace(tzinfo=None).isoformat(),
            "future": (now + timedelta(hours=2)).isoformat(),
        }[observation]
        match.scheduled_start = {
            "future": (now + timedelta(hours=1)).isoformat(),
            "past": (now - timedelta(minutes=10)).isoformat(), "missing": "",
        }[starts]

    monkeypatch.setattr(result_settler, "odds_match", odds)
    db = Mock()
    await result_settler._refresh_clv_for_pending(Mock(), db, bet)
    db.update_closing_odds.assert_not_called()


@pytest.mark.asyncio
async def test_clv_records_observation_and_start_for_a_valid_quote(monkeypatch, bet):
    now = datetime.now(timezone.utc)
    observed = (now - timedelta(seconds=1)).isoformat()
    start = (now + timedelta(hours=1)).isoformat()
    bet["selected_player"] = "Joao Sousa"

    async def odds(match, session):
        match.player_a.book_odds = 1.7
        match.market_status = "prematch"
        match.odds_observed_at = observed
        match.scheduled_start = start

    monkeypatch.setattr(result_settler, "odds_match", odds)
    db = Mock()
    db.update_closing_odds.return_value = True
    assert await result_settler._refresh_clv_for_pending(Mock(), db, bet) is True
    db.update_closing_odds.assert_called_once_with(
        bet["match_url"], 1.7, observed_at=observed, scheduled_start=start,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("selected,quote", [
    ("Unknown Player", 1.7), ("João Sousa", float("nan")),
    ("João Sousa", float("inf")), ("João Sousa", 1.0),
])
async def test_clv_rejects_unknown_selection_and_invalid_prices(monkeypatch, bet, selected, quote):
    now = datetime.now(timezone.utc)
    bet["selected_player"] = selected

    async def odds(match, session):
        match.player_a.book_odds = quote
        match.market_status = "prematch"
        match.odds_observed_at = (now - timedelta(seconds=1)).isoformat()
        match.scheduled_start = (now + timedelta(hours=1)).isoformat()

    monkeypatch.setattr(result_settler, "odds_match", odds)
    db = Mock()
    assert await result_settler._refresh_clv_for_pending(Mock(), db, bet) is False
    db.update_closing_odds.assert_not_called()


@pytest.mark.asyncio
async def test_clv_uses_player_b_price_and_propagates_database_rejection(monkeypatch, bet):
    now = datetime.now(timezone.utc)
    bet["selected_player"] = bet["player_b"]

    async def odds(match, session):
        match.player_a.book_odds = 1.7
        match.player_b.book_odds = 2.4
        match.market_status = "prematch"
        match.odds_observed_at = (now - timedelta(seconds=1)).isoformat()
        match.scheduled_start = (now + timedelta(hours=1)).isoformat()

    monkeypatch.setattr(result_settler, "odds_match", odds)
    db = Mock()
    db.update_closing_odds.return_value = False
    assert await result_settler._refresh_clv_for_pending(Mock(), db, bet) is False
    assert db.update_closing_odds.call_args.args == (bet["match_url"], 2.4)


@pytest.mark.asyncio
async def test_result_summary_marks_missing_clv_unavailable(monkeypatch, bet, capsys):
    _mock_request(monkeypatch, _header("Joao Sousa def. Player Beta 6-3 6-2"))
    db = Mock()
    db.get_pending_bets.return_value = [bet]
    db.settle_bet.return_value = True
    db.get_roi_summary.return_value = {
        "settled": 1, "winrate": 100, "profit": 1.0, "roi": 100,
        "avg_clv": None, "clv_samples": 0,
    }
    assert await result_settler.update_pending_results(Mock(), db) == 1
    db.export_bets_to_excel.assert_called_once()
    assert "CLV Moy : Indisponible" in capsys.readouterr().out
