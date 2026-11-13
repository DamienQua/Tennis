"""Calcul des composantes de l'indice de confiance (Motivation, Tactique, Surface)."""

from datetime import date
import logging
from typing import Optional
import aiohttp
from bs4 import BeautifulSoup
from analysis.match_statistics_analyzer import MatchStatisticsAnalyzer
from analysis.surface_performance_analyzer import SurfacePerformanceAnalyzer
from analysis.tennis_data_fetcher import TennisDataFetcher
from core.models import ConfidenceMetrics

logger = logging.getLogger(__name__)


class MotivationAnalyzer:
    """Évalue la motivation d'un joueur selon la catégorie du tournoi et son volume de jeu."""

    def __init__(
        self,
        data_fetcher: TennisDataFetcher,
        admin_url: str,
        confidence: ConfidenceMetrics,
    ) -> None:
        self.data_fetcher = data_fetcher
        self.admin_url = admin_url
        self.confidence = confidence
        self.surface_analyzer = SurfacePerformanceAnalyzer(data_fetcher, admin_url)

    async def analyze(self, player_id: str, match_id: str, surface: str, flag: int) -> None:
        """Exécute l'analyse de motivation et de rang surface."""
        data_html = await self.fetch_player_activity(player_id, match_id)
        data = BeautifulSoup(data_html, "lxml")
        cat = self.get_tournament_category(data)
        nb_matchs = self.count_matches(data)
        self.calculate_motivation_index(cat, nb_matchs, flag)
        await self.analyze_surface_performance(match_id, surface, flag)

    async def fetch_player_activity(self, player_id: str, match_id: str) -> str:
        player_param = {
            "action": "playerActivity",
            "activityOffset": "0",
            "basic-activity-option": "3",
            "odds": "0",
            "filterType": "basic",
            "playerID": player_id,
            "matchID": match_id,
        }
        return await self.data_fetcher.fetch_data(self.admin_url, player_param)

    @staticmethod
    def get_tournament_category(data: BeautifulSoup) -> str:
        try:
            table = data.find(id="activity-table") if data else None
            if table:
                subheaders = table.find_all(class_="subheader")
                if subheaders:
                    return subheaders[0].text
        except (AttributeError, IndexError):
            pass
        return "250"

    @staticmethod
    def _get_year_index(show_class, year: int) -> int:
        for idx, item in enumerate(show_class):
            if str(year) in item.text:
                return idx + 1
        return -1

    @staticmethod
    def _count_matches_in_year(show_class, start_index: int) -> int:
        count = 0
        for idx in range(start_index, len(show_class)):
            if show_class[idx].text == "Date":
                break
            count += 1
        return count

    def count_matches(self, data: BeautifulSoup) -> int:
        try:
            table = data.find(id="activity-table") if data else None
            if not table:
                return -1
            show_class = table.find_all(class_="show")
            start_index = self._get_year_index(show_class, date.today().year)
            if start_index == -1:
                return -1
            return self._count_matches_in_year(show_class, start_index)
        except (AttributeError, IndexError, TypeError):
            return -1

    def calculate_motivation_index(self, cat: str, nb_matchs: int, flag: int) -> None:
        thresholds = {
            "250": (0, 2),
            "500": (0, 2),
            "1000": (0, float("inf")),
            "Slam": (0, float("inf")),
        }
        score = 0.0
        matched = False
        for key, (low, high) in thresholds.items():
            if key in cat:
                if nb_matchs >= 0:
                    score = 50.0 if low <= nb_matchs < high else 100.0
                matched = True
                break

        if not matched and nb_matchs >= 0:
            score = 50.0 if nb_matchs < 2 else 100.0

        if flag == 0:
            self.confidence.motivation_a = score
        else:
            self.confidence.motivation_b = score

    async def analyze_surface_performance(self, match_id: str, surface: str, flag: int) -> None:
        rank_score = float(await self.surface_analyzer.analyze(match_id, surface, flag))
        if flag == 0:
            self.confidence.surface_rank_a = rank_score
        else:
            self.confidence.surface_rank_b = rank_score


class TacticsAnalyzer:
    """Analyse les statistiques tactiques du dernier affrontement H2H sur surface."""

    def __init__(
        self,
        data_fetcher: TennisDataFetcher,
        admin_url: str,
        confidence: ConfidenceMetrics,
    ) -> None:
        self.data_fetcher = data_fetcher
        self.admin_url = admin_url
        self.confidence = confidence
        self.stats_analyzer = MatchStatisticsAnalyzer()

    async def analyze(self, match_url: str, flag: int) -> None:
        try:
            match_id = self.extract_match_id(match_url)
            if not match_id:
                return
            stats_match = await self.fetch_match_stats(match_id)
            if not stats_match:
                return
            flat_stats = self.stats_analyzer.calculate_serve_return_stats(stats_match, flag)
            self.confidence.tactical_pairs = [
                (flat_stats[i], flat_stats[i + 1]) for i in range(0, len(flat_stats), 2)
            ]
            self.confidence.tiebreak_pair = (
                self.stats_analyzer.calculate_tiebreak_stats(stats_match)
            )
        except (IndexError, ValueError, AttributeError, TypeError, KeyError) as err:
            logger.debug("Stats tactiques indisponibles pour %s : %s", match_url, err)

    @staticmethod
    def extract_match_id(match_url: str) -> str:
        if match_url and "match/" in match_url:
            parts = match_url.split("match/")[1].split("/")
            return parts[0] if parts else ""
        return ""

    async def fetch_match_stats(self, match_id: str) -> BeautifulSoup:
        req = {"action": "showMatchStats", "matchID": match_id, "refresh": "true"}
        stats_match_html = await self.data_fetcher.fetch_data(self.admin_url, req)
        return BeautifulSoup(stats_match_html, "lxml")


async def indice_confiance(
    session: aiohttp.ClientSession,
    admin_url: str,
    player_id: str,
    match_id: str,
    surface: str,
    flag: int = 0,
    choix: str = "",
    match_url: str = "",
    confidence: Optional[ConfidenceMetrics] = None,
) -> ConfidenceMetrics:
    """Point d'entrée typé du calcul de l'indice de confiance."""
    conf = confidence if confidence is not None else ConfidenceMetrics()
    data_fetcher = TennisDataFetcher(session)

    if choix == "Motivation":
        analyzer = MotivationAnalyzer(data_fetcher, admin_url, conf)
        await analyzer.analyze(player_id, match_id, surface, flag)
    elif choix == "Tactique":
        tactics = TacticsAnalyzer(data_fetcher, admin_url, conf)
        await tactics.analyze(match_url, flag)
    elif choix == "Surface":
        surf_analyzer = SurfacePerformanceAnalyzer(data_fetcher, admin_url)
        score = float(await surf_analyzer.analyze(match_id, surface, flag))
        if flag == 0:
            conf.surface_rank_a = score
        else:
            conf.surface_rank_b = score

    return conf