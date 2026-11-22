"""Tests de non-régression pour les correctifs Priorité 2."""

import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from analysis.h2h_stats import DateUtils
from analysis.surface_performance_analyzer import SurfacePerformanceAnalyzer
from analysis.tennis_data_fetcher import TennisDataFetcher
from core.models import MatchAnalysisData, PlayerStats
from main import login
from strategy.generate_match_xlsx import _sanitize_fs_name
from utils.helpers import parse_english_date

odds_mod = importlib.import_module("data_providers.odds_match")


class _FakePostContext:
    def __init__(self, cookies=None, body=""):
        self.cookies = cookies or {}
        self._body = body

    def raise_for_status(self):
        return None

    async def text(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_wordpress_login_rejects_missing_auth_cookie(monkeypatch):
    """Vérifie que login() échoue même en HTTP 200 si aucun cookie WordPress n'est présent."""
    monkeypatch.setenv("TENNISINSIGHT_LOGIN", "user")
    monkeypatch.setenv("TENNISINSIGHT_PASSWORD", "wrong_pass")

    session = MagicMock()
    session.cookie_jar = []
    session.post.return_value = _FakePostContext(
        cookies={}, body='<div id="login_error">Invalid password</div>'
    )

    with pytest.raises(RuntimeError, match="wordpress_logged_in_"):
        await login(session)


@pytest.mark.asyncio
async def test_wordpress_login_accepts_valid_cookie(monkeypatch):
    """Vérifie que login() réussit quand wordpress_logged_in_* est dans la cookie_jar."""
    monkeypatch.setenv("TENNISINSIGHT_LOGIN", "user")
    monkeypatch.setenv("TENNISINSIGHT_PASSWORD", "good_pass")

    session = MagicMock()
    session.cookie_jar = [SimpleNamespace(key="wordpress_logged_in_abc123")]
    session.post.return_value = _FakePostContext(cookies={})

    await login(session)


def test_odds_match_short_surname_no_false_positive_and_accents():
    """Vérifie qu'un nom court ('Li') ne matche pas 'Elina' et que les accents sont gérés."""
    match_false = MatchAnalysisData(
        match_url="https://tennisinsight.com/match/1/2026-wta/r16/li-vs-swiatek",
        player_a=PlayerStats(name="Ann Li"),
        player_b=PlayerStats(name="Iga Swiatek"),
    )
    wrong_html = (
        '{"home-name":"Elina Svitolina","away-name":"Iga Świątek",'
        '"isFinished":false,"maxOdds":3.20,"maxOdds":1.35}'
    )
    assert odds_mod.process_odds(wrong_html, match_false) is False

    good_html = (
        '{"home-name":"Iga Świątek","away-name":"Ann Li",'
        '"isFinished":false,"maxOdds":1.18,"maxOdds":5.10}'
    )
    assert odds_mod.process_odds(good_html, match_false) is True
    assert match_false.player_a.book_odds == 5.10
    assert match_false.player_b.book_odds == 1.18


@pytest.mark.asyncio
async def test_fetch_both_odds_does_not_short_circuit_on_wrong_opponent():
    """Vérifie que fetch_both_odds interroge le 2e joueur si la 1re page n'a pas la paire exacte."""
    html_wrong = (
        '{"home-name":"Carlos Alcaraz","away-name":"Daniil Medvedev",'
        '"isFinished":false,"maxOdds":1.40,"maxOdds":3.10}'
    )
    html_right = (
        '{"home-name":"Carlos Alcaraz","away-name":"Jannik Sinner",'
        '"isFinished":false,"maxOdds":1.85,"maxOdds":1.95}'
    )

    with patch.object(
        odds_mod, "fetch_odds", new=AsyncMock(side_effect=[html_wrong, html_right])
    ) as mock_fetch:
        h1, h2 = await odds_mod.fetch_both_odds(
            MagicMock(), "Carlos Alcaraz", "Jannik Sinner"
        )
        assert mock_fetch.await_count == 2
        assert h1 == html_wrong
        assert h2 == html_right


@pytest.mark.asyncio
async def test_inflight_deduplication_prevents_duplicate_ajax_calls():
    """Vérifie que deux appels concurrents pour le même match_id n'effectuent qu'une requête."""
    TennisDataFetcher._activity_pane_cache.clear()
    SurfacePerformanceAnalyzer._stats_cache.clear()

    fetcher = TennisDataFetcher(MagicMock(), "https://example.test/ajax")
    call_count = 0

    async def fake_fetch_data(url, data=None, method="POST"):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        if data.get("pane") == "activity":
            return '<input id="basic-this-tournament-A" value="At Roland Garros" />'
        return '<table class="table match-preview-statistics-table"></table>'

    fetcher.fetch_data = fake_fetch_data

    t1, t2 = await asyncio.gather(
        fetcher.fetch_tournament_data("match_42"),
        fetcher.fetch_tournament_data("match_42"),
    )
    assert (t1, t2) == ("Roland Garros", "Roland Garros")
    assert call_count == 1

    surf_analyzer = SurfacePerformanceAnalyzer(fetcher, "https://example.test/ajax")
    s1, s2 = await asyncio.gather(
        surf_analyzer.fetch_statistics_html("match_42"),
        surf_analyzer.fetch_statistics_html("match_42"),
    )
    assert s1 == s2
    assert call_count == 2  # 1 pour activity + 1 pour statistics (et non 4)


def test_locale_independent_english_date_parsing():
    """Vérifie le parsing des mois anglais critiques (Feb, May, Aug, Dec) sans locale OS."""
    dt_may = parse_english_date("May 15 2026")
    dt_feb = parse_english_date("Feb 02 2025")
    assert (dt_may.year, dt_may.month, dt_may.day) == (2026, 5, 15)
    assert (dt_feb.year, dt_feb.month, dt_feb.day) == (2025, 2, 2)
    assert DateUtils.parse_date("Aug 28 2026") > 0.0
    assert DateUtils.parse_date("Dec 01 2026") > 0.0


def test_windows_filename_sanitization():
    """Vérifie le nettoyage des caractères interdits Windows dans les chemins Excel."""
    assert _sanitize_fs_name('ATP 500: "Queen\'s" / London?*...') == "ATP_500_Queen's_London"
