"""Tests unitaires pour le filtrage, le matching ELO, l'extraction et les cotes."""

from bs4 import BeautifulSoup
from core.match_filter import MatchFilter
from core.models import MatchAnalysisData, PlayerStats
from core.player_extractor import PlayerExtractor
from data_providers.elo_matcher import EloMatcher
from data_providers.odds_match import process_odds


def test_match_filter_rules():
    """Vérifie les règles d'inclusion, d'exclusion et de déduplication."""
    already = {"https://tennisinsight.com/match/100/2026-atp-paris/r16/a-vs-b"}

    assert MatchFilter.should_process(
        "https://tennisinsight.com/match/100/2026-atp-paris/r16/a-vs-b", already
    ) is False
    assert MatchFilter.should_process(
        "https://tennisinsight.com/match/101/2026-atp-paris/q/a-vs-b", already
    ) is False
    assert MatchFilter.should_process(
        "https://tennisinsight.com/match/102/2026-atp-paris/qf/a-vs-b", already
    ) is True
    assert MatchFilter.should_process(
        "https://tennisinsight.com/match/103/2026-itf/r16/mirra-andreeva-vs-x", already
    ) is True


def test_elo_matcher_alias_and_homonym_protection():
    """Vérifie le matching ELO par surface, alias Gauff et rejet des homonymes."""
    elo_table_sample = (
        "Coco Gauff 2081.8 2044.5 1891.9\n"
        "Juan Manuel Cerundolo 1706.8 1761.8 1561.8\n"
        "Francisco Cerundolo 1803.8 1832.2 1722.8\n"
    )

    elo_gauff, elo_cer = EloMatcher.find_elo_ratings(
        elo_table_sample, "Cori Gauff", "Francisco Cerundolo", "Hard"
    )
    assert elo_gauff == "2081.8"
    assert elo_cer == "1803.8"


def test_odds_match_rejects_homonyms_doubles_and_finished():
    """Vérifie le rejet des homonymes, des matchs de double ('/') et des matchs terminés."""
    match = MatchAnalysisData(
        match_url="https://tennisinsight.com/match/200/2026-atp/r16/f-cerundolo-vs-sinner",
        player_a=PlayerStats(name="Francisco Cerundolo"),
        player_b=PlayerStats(name="Jannik Sinner"),
    )

    wrong_html = (
        '{"home-name":"Juan Manuel Cerundolo","away-name":"Carlos Alcaraz",'
        '"maxOdds":3.40,"maxOdds":1.30}'
    )
    assert process_odds(wrong_html, match) is False

    doubles_html = (
        '{"home-name":"Francisco Cerundolo / T. Etcheverry",'
        '"away-name":"Jannik Sinner / L. Sonego","maxOdds":2.50,"maxOdds":1.50}'
    )
    assert process_odds(doubles_html, match) is False

    finished_and_upcoming_html = (
        '{"home-name":"Jannik Sinner","away-name":"Francisco Cerundolo",'
        '"isFinished":true,"maxOdds":1.10,"maxOdds":6.00}'
        '{"home-name":"Jannik Sinner","away-name":"Francisco Cerundolo",'
        '"isFinished":false,"maxOdds":1.25,"maxOdds":4.10}'
    )
    assert process_odds(finished_and_upcoming_html, match) is True
    assert match.player_a.book_odds == 4.10
    assert match.player_b.book_odds == 1.25


def test_player_extractor_fallback_to_overview():
    """Vérifie l'extraction des IDs joueurs depuis le panneau overview en repli."""
    empty_main = BeautifulSoup("<html><body></body></html>", "lxml")
    overview_html = (
        '<div><a href="/player/?playerid=12345">Player One</a>'
        '<a href="/player/?playerid=67890">Player Two</a></div>'
    )
    soup_overview = BeautifulSoup(overview_html, "lxml")

    id_a, id_b = PlayerExtractor.extract_player_ids(
        "", empty_main, overview_html, soup_overview
    )
    assert (id_a, id_b) == ("12345", "67890")