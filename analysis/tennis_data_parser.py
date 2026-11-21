"""Parsing des pourcentages de victoires et statistiques de match."""

from typing import Any, List, Optional, Tuple
from math import isfinite
import re
from bs4 import BeautifulSoup
from utils.player_identity import names_match


class TennisDataParser:
    """Extrait les ratios de victoires et statistiques de service depuis BeautifulSoup."""

    @staticmethod
    def _extract_single_percentage(percentage_str: str) -> float:
        try:
            cleaned = percentage_str.strip().replace("\t", "")
            parts = cleaned.split("\n\n")
            target = parts[1] if len(parts) > 1 else parts[0]
            val = target.strip().split("%")[0].strip()
            number = float(val.replace(",", "."))
            return number if isfinite(number) and 0 <= number <= 100 else float("nan")
        except (ValueError, IndexError, AttributeError):
            return float("nan")

    @classmethod
    def parse_win_percentages(cls, data: Optional[BeautifulSoup]) -> List[float]:
        """Extrait les pourcentages de victoires sur différentes fenêtres."""
        if not data or not getattr(data, "text", None):
            return []
        text = data.text
        lower_text = text.lower()

        def split_after(marker: str) -> str:
            pos = lower_text.find(marker.lower())
            return text[pos + len(marker):] if pos >= 0 else ""

        match_parts = text.split("Matches")
        win_percentages = [
            match_parts[1] if len(match_parts) > 1 else "",
            match_parts[2] if len(match_parts) > 2 else "",
            split_after("months)"),
            split_after("2000)"),
        ]
        return [cls._extract_single_percentage(part) for part in win_percentages]

    @staticmethod
    def parse_match_statistics(
        stats_match: Optional[BeautifulSoup],
        player_name: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[float], Optional[float], Optional[float]]:
        """Extrait les observations du joueur, sans convertir les absences en zéro."""
        if not stats_match:
            return None, None, None, None
        heading = stats_match.find("h5")
        duration = re.search(r"\b(\d+)\s*m", heading.get_text() if heading else "")
        minutes = int(duration.group(1)) if duration else None
        cols = stats_match.find_all(class_="col-xs-4")
        offset = 0
        if player_name:
            sides = [i for i in (0, 2) if len(cols) > i and names_match(cols[i].get_text(" ", strip=True), player_name)]
            if len(sides) != 1:
                return minutes, None, None, None
            offset = sides[0]

        def _extract_pct(idx: int) -> Optional[float]:
            if len(cols) <= idx + offset:
                return None
            raw = cols[idx + offset].get_text(" ", strip=True)
            percentage = re.match(r"^([\d.,]+)\s*%", raw)
            if not percentage:
                return None
            # TennisInsight emits 0%(/0), 0%(/), or 0%(0/0) for unavailable data.
            if "/" in raw:
                ratio = re.search(r"\(\s*(\d+)\s*/\s*(\d+)\s*\)", raw)
                if not ratio or int(ratio.group(2)) == 0 or int(ratio.group(1)) > int(ratio.group(2)):
                    return None
            try:
                value = float(percentage.group(1).replace(",", "."))
            except ValueError:
                return None
            return value if isfinite(value) and 0 <= value <= 100 else None

        return minutes, _extract_pct(9), _extract_pct(12), _extract_pct(18)


class StatisticsProcessor:
    """Façade de traitement statistique."""

    @staticmethod
    def calculate_win_percentages(data: Optional[BeautifulSoup]) -> List[float]:
        return TennisDataParser.parse_win_percentages(data)

    @staticmethod
    async def process_match_statistics(
        data_fetcher, matches_list: List[Any], m_i: int, player_name: Optional[str] = None
    ) -> Tuple[Optional[int], Optional[float], Optional[float], Optional[float]]:
        stats_match = await data_fetcher.fetch_match_statistics(matches_list[m_i])
        return TennisDataParser.parse_match_statistics(stats_match, player_name)
