"""
Module for parsing player win percentages, match statistics, and activity data.
"""

from typing import Any, List, Optional, Tuple
from bs4 import BeautifulSoup


class TennisDataParser:
    """Parses player win percentages, match history, and performance statistics."""

    @staticmethod
    def _extract_single_percentage(percentage_str: str) -> float:
        try:
            cleaned = percentage_str.replace("N/A", "0").strip().replace("\t", "")
            parts = cleaned.split("\n\n")
            target = parts[1] if len(parts) > 1 else parts[0]
            val = target.replace("N/A", "0").strip().split("%")[0].strip()
            return float(val) if val else 0.0
        except (ValueError, IndexError, AttributeError):
            return 0.0

    @classmethod
    def parse_win_percentages(cls, data: Optional[BeautifulSoup]) -> List[float]:
        """Parses win percentages across all surfaces from HTML."""
        if not data or not getattr(data, "text", None):
            return []
        text = data.text
        lower_text = text.lower()

        def split_after(marker: str) -> List[str]:
            """Splits string after specified delimiter safely."""
            pos = lower_text.find(marker.lower())
            return [text[pos + len(marker):]] if pos >= 0 else []

        win_percentages = (
            text.split("Matches")[1:3] +
            split_after("months)") +
            split_after("2000)")
        )
        return [cls._extract_single_percentage(part) for part in win_percentages]

    @staticmethod
    def parse_match_statistics(
            stats_match: Optional[BeautifulSoup]
    ) -> Tuple[int, float, float, float]:
        """Parses serve and return statistics from match HTML."""
        if not stats_match:
            return 0, 0.0, 0.0, 0.0
        try:
            heading = stats_match.find("h5")
            min_tour = (
                int(heading.text.split(" m")[0])
                if heading and " m" in heading.text
                else 0
            )
            cols = stats_match.find_all(class_="col-xs-4")

            def _extract_pct(idx: int) -> float:
                if len(cols) <= idx:
                    return 0.0
                return float(cols[idx].text.replace("N/A", "0").strip().split("%")[0])

            per_first_serve = _extract_pct(9)
            points_first_serve = _extract_pct(12)
            per_save_bp = _extract_pct(18)
            return min_tour, per_first_serve, points_first_serve, per_save_bp
        except (IndexError, ValueError, AttributeError, TypeError):
            return 0, 0.0, 0.0, 0.0


class StatisticsProcessor:
    """Delegates statistical parsing operations for tennis match data."""

    @staticmethod
    def calculate_win_percentages(data: Optional[BeautifulSoup]) -> List[float]:
        """Calculates win percentages from parsed activity data."""
        return TennisDataParser.parse_win_percentages(data)

    @staticmethod
    async def process_match_statistics(
            data_fetcher, matches_list: List[Any], m_i: int, *args, **kwargs
    ) -> Tuple[int, float, float, float]:
        """Processes match statistics asynchronously for given match index."""
        stats_match = await data_fetcher.fetch_match_statistics(matches_list[m_i])
        return TennisDataParser.parse_match_statistics(stats_match)
