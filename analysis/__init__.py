"""
Analysis module for player statistics, head-to-head records,
confidence indices, and match performance.
"""

from .compare_indice import compare_indice, IndiceComparator
from .compare_players import compare_players, AttributeComparator
from .h2h_stats import H2HStats, DateUtils
from .h2h_table import h2h_table, MatchContext, H2HDataProcessor
from .indice_confiance import indice_confiance
from .last_matchs import last_matchs, TennisMatchAnalyzer
from .tennis_data_fetcher import TennisDataFetcher
from .tennis_data_parser import TennisDataParser, StatisticsProcessor
from .match_statistics_analyzer import MatchStatisticsAnalyzer
from .match_statistics_processor import MatchStatisticsProcessor
from .surface_performance_analyzer import SurfacePerformanceAnalyzer

__all__ = [
    "compare_indice",
    "IndiceComparator",
    "compare_players",
    "AttributeComparator",
    "H2HStats",
    "DateUtils",
    "h2h_table",
    "MatchContext",
    "H2HDataProcessor",
    "indice_confiance",
    "last_matchs",
    "TennisMatchAnalyzer",
    "TennisDataParser",
    "TennisDataFetcher",
    "StatisticsProcessor",
    "MatchStatisticsAnalyzer",
    "MatchStatisticsProcessor",
    "SurfacePerformanceAnalyzer",
]
