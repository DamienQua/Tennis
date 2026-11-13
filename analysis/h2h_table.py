"""Extraction et analyse du tableau Head-to-Head (H2H)."""

from dataclasses import dataclass
import re
from typing import Any, Tuple
import aiohttp
from bs4 import BeautifulSoup
from analysis.h2h_stats import H2HStats, DateUtils
from analysis.indice_confiance import indice_confiance
from core.models import H2HMetrics, MatchAnalysisData


@dataclass
class MatchContext:
    """Contexte réseau et match pour le traitement H2H."""

    surface: str
    admin_url: str
    header: dict
    match_id: str


class H2HDataProcessor:
    """Parse les lignes HTML H2H (compatible MatchAnalysisData et vecteur match_vs)."""

    def __init__(self, data: BeautifulSoup, match: Any) -> None:
        self.data = data
        self.match = match
        self._is_typed = isinstance(match, MatchAnalysisData)
        name_a = match.player_a.name if self._is_typed else str(match[2])
        name_b = match.player_b.name if self._is_typed else str(match[3])
        self.surface = match.surface if self._is_typed else str(match[1])
        self.player_a_name = name_a
        self.stats = H2HStats(name_a, name_b)
        self.go_url = ""
        self.flag = 0

    def process(self) -> None:
        """Exécute le comptage et le parsing des confrontations passées."""
        self._process_h2h_count()
        self._process_h2h_matches()
        self._apply_metrics()

    def process_h2h_data(self) -> None:
        """Alias rétrocompatible de process()."""
        self.process()

    def _reset_metrics(self) -> None:
        if self._is_typed:
            self.match.h2h = H2HMetrics()
        else:
            self.match[6:14] = [0] * 8

    def _apply_metrics(self) -> None:
        metrics = self.stats.to_metrics()
        if self._is_typed:
            self.match.h2h = metrics
        elif self.stats.p_a.wins_all + self.stats.p_b.wins_all == 0:
            self.match[6:14] = [0] * 8
        else:
            self.match[6:14] = (
                metrics.all_time + metrics.last_year + metrics.surface + metrics.games
            )

    def _process_h2h_count(self) -> None:
        if not self.data or not getattr(self.data, "text", None) or "series " not in self.data.text:
            self._reset_metrics()
            return
        ind = 1 if "tied" in self.data.text else 0
        for idx in range(2):
            try:
                split_series = self.data.text.strip().split("series ")[1]
                val = split_series.split(" ")[ind].split("-")[idx].split("\n")[0]
                self.stats.h2h_nb += int(val)
            except (IndexError, ValueError):
                pass
        if self.stats.h2h_nb == 0:
            self._reset_metrics()

    @staticmethod
    def _parse_row_score(raw_score: str) -> str:
        clean_score = re.sub(r"[\(\[].*?[\)\]]", "", raw_score)
        res = clean_score.replace("ret.", " ").replace("w/o", "").strip()
        return res if res else "0-0 0-0"

    @classmethod
    def _extract_match_details(cls, row_elem) -> Tuple[float, str, str, str]:
        """Extrait date, surface, vainqueur et score depuis une ligne <tr>."""
        tds = row_elem.find_all("td")
        if len(tds) >= 5:
            date_ms = DateUtils.parse_date(tds[0].text.strip())
            surface_m = tds[2].text.split(",")[0].strip()
            raw_winner = tds[3].text.strip()
            winner = re.sub(r"[\(\[].*?[\)\]]", "", raw_winner).split("  d")[0].strip()
            score = cls._parse_row_score(tds[4].text.strip())
            return date_ms, surface_m, winner, score

        lines = [line.strip() for line in row_elem.text.strip().split("\n") if line.strip()]
        tab_parts = row_elem.text.strip().split("\t")
        date_ms = DateUtils.parse_date(tab_parts[0].strip()) if tab_parts else 0.0
        surface_m = lines[5].split(",")[0].strip() if len(lines) > 5 else ""
        raw_winner = lines[7].strip() if len(lines) > 7 else ""
        winner = re.sub(r"[\(\[].*?[\)\]]", "", raw_winner).split("  d")[0].strip()
        raw_score = lines[9].strip() if len(lines) > 9 else ""
        return date_ms, surface_m, winner, cls._parse_row_score(raw_score)

    def _update_go_flag(self, row_elem, surface_m: str, winner: str) -> None:
        if self.go_url == "" and surface_m and surface_m in row_elem.text:
            links = row_elem.find_all("a")
            if links:
                self.go_url = links[-1].get("href", "")
                self.flag = 0 if winner == self.player_a_name else 1

    def _process_h2h_matches(self) -> None:
        h2h_elem = self.data.find(class_="h2h-matches") if self.data else None
        if not h2h_elem:
            return
        for row_elem in h2h_elem.find_all("tr")[1:]:
            date_ms, surface_m, winner, score = self._extract_match_details(row_elem)
            self.stats.update_stats(winner, date_ms, surface_m, score, self.surface)
            self._update_go_flag(row_elem, surface_m, winner)


async def h2h_table(
    data: BeautifulSoup,
    match: MatchAnalysisData,
    session: aiohttp.ClientSession,
    match_context: MatchContext,
) -> MatchAnalysisData:
    """Analyse les confrontations H2H et met à jour les métriques de confiance."""
    processor = H2HDataProcessor(data, match)
    processor.process()

    conf = match.confidence
    if processor.stats.win_a_sur > 0:
        conf.h2h_surface_bonus_a = 2 * conf.surface_rank_a
    if processor.stats.win_b_sur > 0:
        conf.h2h_surface_bonus_b = 2 * conf.surface_rank_b

    if processor.go_url:
        await indice_confiance(
            session=session,
            admin_url=match_context.admin_url,
            player_id="",
            match_id=match_context.match_id,
            surface=match_context.surface,
            flag=processor.flag,
            choix="Tactique",
            match_url=processor.go_url,
            confidence=conf,
        )
    return match