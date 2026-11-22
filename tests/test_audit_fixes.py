"""Tests de non-régression couvrant les 12 anomalies de l'audit croisé."""

from datetime import datetime, timezone
import importlib
import json
import ssl
from unittest.mock import AsyncMock, MagicMock, patch
from bs4 import BeautifulSoup
import pandas as pd
import pytest

from analysis.compare_players import _DEFAULT_WEIGHTS, compare_players
from analysis.indice_confiance import TacticsAnalyzer
from analysis.match_statistics_analyzer import MatchStatisticsAnalyzer
from backtest.calibrate_weights import _predict_compare_players_probs, calibrate_from_dataframe
from backtest.historical_odds import HistoricalOddsProvider
from core.analyze_match import analyze_match
from core.database import TennisDatabase
from core.match_filter import MatchFilter
from core.models import ConfidenceMetrics, MatchAnalysisData, PlayerStats
from core.tournament_extractor import check_match_prematch_status, who_is_favorite
from strategy.alpha_strategy import evaluate_alpha_strategy
from strategy.email_notifier import send_daily_email
from strategy.result_settler import _parse_match_outcome

odds_mod = importlib.import_module("data_providers.odds_match")
cp_mod = importlib.import_module("analysis.compare_players")


def test_p1_who_is_favorite_real_set_handicap_zverev_alcaraz():
    """P1 : +1.5 (Zverev) vs -1.5 (Alcaraz) doit désigner Alcaraz [0, 1] comme favori."""
    html = """
    <div class="mp_bio_left"><ul><li>Rank: 1</li><li>+1.5</li></ul></div>
    <div class="mp_bio_right"><ul><li>Rank: 3</li><li>-1.5</li></ul></div>
    """
    soup = BeautifulSoup(html, "lxml")
    assert who_is_favorite(soup) == [0, 1]
    assert who_is_favorite(soup, book_odds=(2.72, 1.50)) == [0, 1]
    assert who_is_favorite(soup, book_odds=(1.45, 2.85)) == [1, 0]


def test_p1_calibration_evaluates_exact_compare_players_and_blocks_future_weights(
    tmp_path, monkeypatch
):
    """P1 : la calibration évalue le modèle final et as_of_date bloque toute fuite future."""
    rows = []
    for idx in range(60):
        rows.append({
            "Date": f"2025-{(idx // 28) + 1:02d}-{(idx % 28) + 1:02d}",
            "Surface": "Hard",
            "Comment": "Completed",
            "Winner": "Fav Player" if idx % 5 != 0 else "Dog Player",
            "Loser": "Dog Player" if idx % 5 != 0 else "Fav Player",
            "WRank": 5 if idx % 5 != 0 else 80,
            "LRank": 80 if idx % 5 != 0 else 5,
        })
    out_json = tmp_path / "calibrated.json"
    cal = calibrate_from_dataframe(pd.DataFrame(rows), output_path=str(out_json))
    assert cal["hard"]["brier_after"] <= cal["hard"]["brier_before"]
    assert cal["hard"]["trained_until"] == "2025-03-04"

    # Injecte des poids manifestement différents avec trained_until=2025-12-31
    custom_json = tmp_path / "future_weights.json"
    custom_json.write_text(
        json.dumps({
            "hard": {
                "rank": 15.0,
                "form": 5.0,
                "surface": 5.0,
                "elo": 0.45,
                "trj": 0.90,
                "accepted": True,
                "trained_until": "2025-12-31",
                "brier_before": 0.24,
                "brier_after": 0.20,
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(cp_mod, "CALIBRATED_WEIGHTS_PATH", str(custom_json))

    # Match de 2024 : ne doit PAS utiliser les poids entraînés jusqu'en 2025-12-31
    w_past = cp_mod._load_surface_weights("Hard", as_of_date="2024-06-01")
    assert w_past["rank"] == _DEFAULT_WEIGHTS["hard"]["rank"]
    # Match de 2026 : peut les utiliser
    w_future = cp_mod._load_surface_weights("Hard", as_of_date="2026-01-15")
    assert w_future["rank"] == 15.0
    assert _predict_compare_players_probs(
        pd.DataFrame([[0, 0, 0, 0, 1, 0, 1, 0, 0, 0]]).to_numpy(dtype=float),
        pd.Series([5.0, 20.0, 30.0, 0.15]).to_numpy(dtype=float),
    )[0] == pytest.approx(0.98)


def test_p1_odds_match_never_falls_back_on_finished_event():
    """P1 : un match isFinished:true ne doit jamais être réaccepté via le fallback global."""
    match = MatchAnalysisData(
        match_url="https://tennisinsight.com/match/260684301/2026-turin/f/zverev-vs-alcaraz",
        player_a=PlayerStats(name="Alexander Zverev"),
        player_b=PlayerStats(name="Carlos Alcaraz"),
    )
    finished_only = (
        '{"home-name":"Alexander Zverev","away-name":"Carlos Alcaraz",'
        '"isFinished":true,"maxOdds":3.40,"maxOdds":1.30}'
    )
    assert odds_mod.process_odds(finished_only, match) is False
    assert match.player_a.book_odds == 0.0
    assert match.player_b.book_odds == 0.0


def test_p1_alpha_rejects_match_without_source_stats():
    """P1 : un match avec uniquement ELO + cotes bookmaker (aucune stat de forme) est rejeté."""
    match = MatchAnalysisData(
        match_url="https://tennisinsight.com/match/1/2026-atp/r16/a-vs-b",
        surface="Hard",
        player_a=PlayerStats(name="Player A", elo=2100.0, book_odds=1.80),
        player_b=PlayerStats(name="Player B", elo=1800.0, book_odds=2.10),
    )
    compare_players(match)
    res = evaluate_alpha_strategy(match)
    assert res["bet_recommended"] is False
    assert res["signal_j1"] == "Données incomplètes"


def test_p1_historical_odds_disambiguates_repeated_meetings(tmp_path):
    """P1 : deux confrontations dans la même année sont distinguées par tournoi/date."""
    df = pd.DataFrame([
        {
            "Date": "2026-01-19",
            "Tournament": "Australian Open",
            "Round": "Semifinals",
            "Winner": "Alcaraz C.",
            "Loser": "Zverev A.",
            "B365W": 1.20,
            "B365L": 4.50,
            "PSW": 1.22,
            "PSL": 4.60,
        },
        {
            "Date": "2026-11-22",
            "Tournament": "Turin ATP Finals",
            "Round": "The Final",
            "Winner": "Zverev A.",
            "Loser": "Alcaraz C.",
            "B365W": 2.70,
            "B365L": 1.50,
            "PSW": 2.75,
            "PSL": 1.52,
        },
    ])
    df.to_excel(tmp_path / "atp_2026.xlsx", index=False)
    provider = HistoricalOddsProvider(data_dir=str(tmp_path))

    # Sans contexte -> ambigu -> None
    assert provider.get_match_odds("Alexander Zverev", "Carlos Alcaraz", 2026, "atp") is None

    # Avec tournoi Turin -> retourne bien novembre et non janvier
    turin = provider.get_match_odds(
        "Alexander Zverev", "Carlos Alcaraz", 2026, "atp", tournament="Turin ATP WTF"
    )
    assert turin is not None
    assert "Turin" in turin["tournament"]
    assert turin["winner"] == "Alexander Zverev"


def test_p1_result_settler_disambiguates_same_surname_brothers():
    """P1 : 'Juan Manuel Cerundolo def. Francisco Cerundolo' renvoie bien Juan Manuel."""
    html = (
        '<div class="wrapper"><div class="match-preview-header">'
        "Buenos Aires: Juan Manuel Cerundolo def. Francisco Cerundolo 6-2 6-4"
        "</div></div>"
    )
    winner, is_void = _parse_match_outcome(
        html, player_a="Francisco Cerundolo", player_b="Juan Manuel Cerundolo"
    )
    assert winner == "Juan Manuel Cerundolo"
    assert is_void is False

    # Si seul le nom de famille ambigu apparaît -> refuse de trancher (None)
    ambiguous_html = (
        '<div class="wrapper"><div class="match-preview-header">'
        "Cerundolo def. Cerundolo 6-2 6-4"
        "</div></div>"
    )
    assert _parse_match_outcome(
        ambiguous_html, player_a="Francisco Cerundolo", player_b="Juan Manuel Cerundolo"
    ) == (None, False)


def test_p2_trailing_slash_url_deduplication_filter_and_db(tmp_path):
    """P2 : une barre finale '/' ne contourne ni MatchFilter ni TennisDatabase."""
    url_no_slash = "https://tennisinsight.com/match/260684301/2026-turin-atp-wtf/f/zverev-vs-alcaraz"
    url_slash = f"{url_no_slash}/"

    assert MatchFilter.should_process(url_slash, already_processed={url_no_slash}) is False
    assert MatchFilter.should_process(url_no_slash, already_processed={url_slash}) is False

    db = TennisDatabase(db_path=str(tmp_path / "isolated.db"))
    daily = str(tmp_path / "Matchs.txt")
    m1 = MatchAnalysisData(match_url=url_no_slash, tournament="Turin", surface="Indoor Hard")
    m2 = MatchAnalysisData(match_url=url_slash, tournament="Turin", surface="Indoor Hard")
    assert db.save_match(m1, daily_file=daily) is True
    assert db.save_match(m2, daily_file=daily) is False
    assert db.is_match_analyzed(url_slash) is True

    alpha_res = {
        "bet_recommended": True,
        "selected_player": "Carlos Alcaraz",
        "book_odds": 1.65,
        "model_odds": 1.35,
        "model_prob": 0.68,
        "ev_percent": 12.2,
        "elo_diff": 180.0,
        "kelly_stake_pct": 2.0,
    }
    assert db.save_bet(m1, alpha_res) is True
    assert db.save_bet(m2, alpha_res) is False


def test_p2_custom_database_does_not_implicitly_restore_prod_dump(tmp_path):
    """P2 : une base personnalisée ne restaure jamais implicitement tennis_ai_dump.sql."""
    db = TennisDatabase(db_path=str(tmp_path / "fresh_isolated.db"))
    assert db.load_reviewed_urls() == set()
    assert db.get_pending_bets() == []


@patch("smtplib.SMTP")
def test_p2_smtp_starttls_uses_verified_ssl_context(mock_smtp):
    """P2 : starttls() reçoit un SSLContext vérifié (CERT_REQUIRED + check_hostname=True)."""
    mock_instance = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_instance

    cfg = {
        "host": "smtp.gmail.com",
        "port": "587",
        "user": "test@gmail.com",
        "password": "secret",
        "recipient": "dest@gmail.com",
    }
    assert send_daily_email([], total_matches=0, config=cfg) is True
    _, kwargs = mock_instance.starttls.call_args
    ctx = kwargs.get("context")
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED


@pytest.mark.asyncio
async def test_p2_tiebreak_stats_respects_flag_orientation():
    """P2 : un tie-break remporté par J2 (flag=1) renvoie (0.0, 100.0) et non (100.0, 0.0)."""
    html = '<div class="col-xs-12"><h4>7-6(4) 6-4</h4></div>'
    soup = BeautifulSoup(html, "lxml")
    analyzer = MatchStatisticsAnalyzer()

    assert analyzer.calculate_tiebreak_stats(soup, flag=0) == (100.0, 0.0)
    assert analyzer.calculate_tiebreak_stats(soup, flag=1) == (0.0, 100.0)

    conf = ConfidenceMetrics()
    fetcher = MagicMock()
    fetcher.fetch_data = AsyncMock(return_value=html)
    tactics = TacticsAnalyzer(fetcher, "https://example.test", conf)
    await tactics.analyze("https://tennisinsight.com/match/999/", flag=1)
    assert conf.tiebreak_pair == (0.0, 100.0)


@pytest.mark.asyncio
async def test_p2_prematch_cutoff_blocks_started_or_finished_match():
    """P2 : un match passé son horaire GMT ou terminé est bloqué par analyze_match."""
    soup_started = BeautifulSoup(
        '<div class="match-preview-header">Nov 22 2026 17:13 GMT</div>', "lxml"
    )
    now_after = datetime(2026, 11, 22, 18, 27, tzinfo=timezone.utc)
    now_before = datetime(2026, 11, 22, 16, 0, tzinfo=timezone.utc)

    ok_before, _ = check_match_prematch_status(soup_started, None, now_utc=now_before)
    ok_after, reason = check_match_prematch_status(soup_started, None, now_utc=now_after)
    assert ok_before is True
    assert ok_after is False
    assert "match_started" in reason

    finished_parsed = {
        "match_id": "260684301",
        "soup_main": BeautifulSoup(
            '<div class="match-preview-header">Carlos Alcaraz def. Alexander Zverev 6-4 6-3</div>',
            "lxml",
        ),
        "soup_overview": BeautifulSoup("", "lxml"),
        "ids": ("1", "2"),
    }
    with patch("core.analyze_match._fetch_match_soups", new=AsyncMock(return_value=finished_parsed)):
        result = await analyze_match(
            MagicMock(), {}, "https://tennisinsight.com/match/260684301/2026-turin/f/a-vs-b/", [], ""
        )
        assert result is None
