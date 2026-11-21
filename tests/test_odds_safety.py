"""Offline regressions for event identity, market boundaries and price provenance."""

from datetime import datetime, timedelta, timezone
from html import escape
import json
from unittest.mock import AsyncMock

import pytest

from core.models import MatchAnalysisData, PlayerStats
import importlib

odds_module = importlib.import_module("data_providers.odds_match")


def match():
    return MatchAnalysisData(
        match_url="https://example.test/match/1",
        player_a=PlayerStats(name="Francisco Cerundolo"),
        player_b=PlayerStats(name="Jannik Sinner"),
    )


def event(**overrides):
    value = {
        "home-name": "Francisco Cerundolo",
        "away-name": "Jannik Sinner",
        "status": "scheduled",
        "startTime": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "markets": [{"name": "Match Winner", "maxOdds": [4.1, 1.25]}],
    }
    value.update(overrides)
    return value


@pytest.mark.parametrize("encode", [
    json.dumps,
    lambda value: '<div data-events="' + escape(json.dumps(value), quote=True) + '"></div>',
    lambda value: "<script>var events = " + json.dumps(json.dumps(value)) + ";</script>",
    lambda value: json.dumps(value).replace('"', '\\"'),
])
def test_parses_json_and_escaped_html_with_metadata(encode):
    data = match()
    page = odds_module._OddsPage(encode(event()))
    assert odds_module.process_odds(page, data)
    assert (data.player_a.book_odds, data.player_b.book_odds) == (4.1, 1.25)
    assert data.market_status == "prematch"
    assert data.odds_observed_at == page.observed_at
    assert datetime.fromisoformat(data.scheduled_start).utcoffset() == timedelta(0)


@pytest.mark.parametrize("status", ["finished", "live", "suspended", "", None])
def test_unknown_live_or_finished_events_are_rejected(status):
    data = match()
    data.player_a.book_odds, data.player_b.book_odds = 2.0, 2.0
    assert not odds_module.process_odds(json.dumps(event(status=status)), data)
    assert (data.player_a.book_odds, data.player_b.book_odds) == (0.0, 0.0)
    assert data.odds_observed_at == ""


def test_nonfinished_flag_alone_is_not_prematch_proof():
    item = event(isFinished=False)
    del item["status"]
    assert not odds_module.process_odds(json.dumps(item), match())


@pytest.mark.parametrize("updates", [
    {"home-name": "Juan Manuel Cerundolo"},
    {"away-name": "Carlos Alcaraz"},
    {"home-name": "Francisco Cerundolo / Tomas Etcheverry"},
    {"startTime": "2020-01-01T00:00:00Z"},
    {"isLive": True},
    {"isFinished": True},
])
def test_invalid_identity_or_status_is_rejected(updates):
    assert not odds_module.process_odds(json.dumps(event(**updates)), match())


def test_two_matching_events_cannot_choose_the_first_prices():
    payload = [event(status="finished"), event()]
    data = match()
    assert not odds_module.process_odds(json.dumps(payload), data)
    assert data.market_status == "unknown"


@pytest.mark.parametrize("markets", [
    [{"name": "First Set Winner", "maxOdds": [4.1, 1.25]}],
    [{"name": "Match Winner", "maxOdds": 4.1}, {"name": "First Set Winner", "maxOdds": 1.25}],
    [{"name": "Match Winner", "period": "set1", "maxOdds": [4.1, 1.25]}],
    [{"name": "Match Winner", "maxOdds": [4.1, 1.25, 2.0]}],
    [{"name": "Match Winner", "maxOdds": [True, 1.25]}],
    [{"name": "Match Winner", "maxOdds": [float("nan"), 1.25]}],
    [{"name": "Match Winner", "maxOdds": [4.1, 1.0]}],
    [{"maxOdds": [4.1, 1.25]}],
])
def test_prices_must_come_from_one_identified_match_winner_market(markets):
    assert not odds_module.process_odds(json.dumps(event(markets=markets)), match())


def test_outcome_names_define_price_order_and_aliases():
    data = match()
    payload = event(markets=[{
        "name": "Match Winner", "outcomes": [
            {"name": "Jannik Sinner", "maxOdds": 1.25},
            {"name": "Francisco Cerúndolo", "maxOdds": 4.1},
        ],
    }])
    assert odds_module.process_odds(json.dumps(payload), data)
    assert (data.player_a.book_odds, data.player_b.book_odds) == (4.1, 1.25)


def test_reverse_event_order_and_epoch_timestamp():
    data = match()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    payload = event(**{
        "home-name": "Jannik Sinner", "away-name": "Francisco Cerundolo",
        "startTime": int(start.timestamp() * 1000),
        "markets": [{"name": "Moneyline", "avgOdds": {"home": 1.25, "away": 4.1}}],
    })
    assert odds_module.process_odds(json.dumps(payload), data)
    assert (data.player_a.book_odds, data.player_b.book_odds) == (4.1, 1.25)


@pytest.mark.asyncio
async def test_second_search_only_when_target_is_absent(monkeypatch):
    target = json.dumps(event())
    other = json.dumps(event(**{"away-name": "Carlos Alcaraz"}))
    fetch = AsyncMock(side_effect=[other, target])
    monkeypatch.setattr(odds_module, "fetch_odds", fetch)
    pages = await odds_module.fetch_both_odds(object(), "Francisco Cerundolo", "Jannik Sinner")
    assert pages == (other, target)
    assert fetch.await_count == 2
    data = match()
    odds_module.apply_odds_data(*pages, data)
    assert data.market_status == "prematch"


@pytest.mark.asyncio
async def test_second_search_cannot_override_rejected_target(monkeypatch):
    rejected = json.dumps(event(status="finished"))
    valid = json.dumps(event())
    fetch = AsyncMock(side_effect=[rejected, valid])
    monkeypatch.setattr(odds_module, "fetch_odds", fetch)
    pages = await odds_module.fetch_both_odds(object(), "Francisco Cerundolo", "Jannik Sinner")
    assert pages == (rejected, "")
    assert fetch.await_count == 1
    data = match()
    odds_module.apply_odds_data(rejected, valid, data)
    assert data.market_status == "finished"
    assert data.player_a.book_odds == data.player_b.book_odds == 0.0


def test_unidentified_raw_prices_never_form_a_market():
    payload = event()
    del payload["markets"]
    encoded = json.dumps(payload)[:-1] + ', "maxOdds": 4.1, "maxOdds": 1.25}'
    assert not odds_module.process_odds(encoded, match())


def test_prices_from_a_nested_other_event_are_not_reused():
    payload = event(markets=[])
    payload["related"] = event(**{"away-name": "Carlos Alcaraz"})
    assert not odds_module.process_odds(json.dumps(payload), match())


@pytest.mark.parametrize("schedule", [
    {"startTime": "2027-01-01T12:00:00"},
    {"scheduledStart": "2020-01-01T12:00:00Z"},
    {"startTime": None},
    {"startTime": float("nan")},
])
def test_unverifiable_or_conflicting_schedule_is_rejected(schedule):
    assert not odds_module.process_odds(json.dumps(event(**schedule)), match())


def test_duplicate_identity_fields_are_ambiguous_and_cannot_trigger_fallback():
    payload = json.dumps(event())[:-1] + ',"home-name":"Juan Manuel Cerundolo"}'
    data = match()
    odds_module.apply_odds_data(payload, json.dumps(event()), data)
    assert data.player_a.book_odds == 0.0
    assert data.market_status == "unknown"


@pytest.mark.parametrize("flags", [{"status": "closed"}, {"isSuspended": True}])
def test_closed_or_suspended_market_is_rejected(flags):
    market = {"name": "Match Winner", "maxOdds": [4.1, 1.25], **flags}
    assert not odds_module.process_odds(json.dumps(event(markets=[market])), match())


def test_mixed_normal_and_escaped_event_payloads_remain_identifiable():
    other = json.dumps(event(**{"away-name": "Carlos Alcaraz"}))
    target = json.dumps(json.dumps(event()))
    data = match()
    assert odds_module.process_odds("<script>" + other + ";" + target + "</script>", data)


def test_exact_duplicate_event_payload_does_not_create_false_ambiguity():
    payload = event()
    assert odds_module.process_odds(json.dumps([payload, payload]), match())


def test_json_string_inside_json_container_preserves_unicode_names():
    payload = event(**{"home-name": "Francisco Cerúndolo"})
    wrapped = json.dumps({"data": json.dumps(payload, ensure_ascii=False)})
    assert odds_module.process_odds(wrapped, match())


@pytest.mark.parametrize("observed", [
    None, "", "invalid", "2026-01-01T12:00:00",
    (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
])
def test_invalid_observation_time_cannot_assign_odds_or_trigger_fallback(observed):
    page = odds_module._OddsPage(json.dumps(event()))
    page.observed_at = observed
    data = match()
    odds_module.apply_odds_data(page, json.dumps(event()), data)
    assert data.player_a.book_odds == data.player_b.book_odds == 0.0
    assert data.odds_observed_at == ""


def test_observation_time_with_explicit_offset_is_normalized_to_utc():
    page = odds_module._OddsPage(json.dumps(event()))
    observed = datetime.now(timezone(timedelta(hours=2))) - timedelta(seconds=1)
    page.observed_at = observed.isoformat()
    data = match()
    assert odds_module.process_odds(page, data)
    assert datetime.fromisoformat(data.odds_observed_at) == observed
    assert data.odds_observed_at.endswith("+00:00")


@pytest.mark.parametrize("flags", [
    {"inPlay": "TRUE"}, {"isStarted": "1"}, {"isSuspended": True},
    {"isClosed": True}, {"isFinished": "TRUE"},
])
def test_conflicting_event_flags_override_scheduled_status(flags):
    assert not odds_module.process_odds(json.dumps(event(**flags)), match())


@pytest.mark.parametrize("flags", [
    {"inPlay": True}, {"isStarted": "TRUE"}, {"status": "Suspended"},
])
def test_unavailable_outcome_or_market_cannot_supply_prices(flags):
    market = {"name": "Match Winner", "maxOdds": [4.1, 1.25], **flags}
    assert not odds_module.process_odds(json.dumps(event(markets=[market])), match())
    market = {"name": "Match Winner", "outcomes": [
        {"name": "Francisco Cerundolo", "price": 4.1, **flags},
        {"name": "Jannik Sinner", "price": 1.25},
    ]}
    assert not odds_module.process_odds(json.dumps(event(markets=[market])), match())


def test_conflicting_market_labels_cannot_promote_first_set_odds():
    market = {"name": "Match Winner", "marketName": "First Set Winner", "maxOdds": [4.1, 1.25]}
    assert not odds_module.process_odds(json.dumps(event(markets=[market])), match())


def test_identical_schedule_in_different_offsets_is_consistent():
    payload = event()
    start = datetime.fromisoformat(payload["startTime"])
    payload["scheduledStart"] = start.astimezone(timezone(timedelta(hours=2))).isoformat()
    assert odds_module.process_odds(json.dumps(payload), match())
