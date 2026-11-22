"""Extraction et analyse du tableau Head-to-Head (H2H)."""

from dataclasses import dataclass
import logging
import re
from typing import List, Optional, Tuple
import aiohttp
from bs4 import BeautifulSoup
from analysis.h2h_stats import H2HStats, DateUtils, _matches_player
from analysis.indice_confiance import indice_confiance
from core.models import H2HMetrics, MatchAnalysisData
from utils.helpers import normalize_surface

logger = logging.getLogger(__name__)

_SURFACE_RE = re.compile(r"\b(?:indoor\s+hard|hard|clay|grass|carpet)\b", re.IGNORECASE)
_SCORE_RE = re.compile(r"(?:\b\d{1,2}-\d{1,2}\b|\bw/o\b|\bwalkover\b|\bret\.)", re.IGNORECASE)
_DEFEAT_SPLIT_RE = re.compile(r"\s+(?:[Dd]ef\.?|[Dd]efeated|d\.?)(?=\s|$)")


@dataclass
class MatchContext:
    """Contexte réseau et match pour le traitement H2H."""

    surface: str
    admin_url: str
    header: dict
    match_id: str


def _same_surface_bucket(target_surface: str, row_surface: str) -> bool:
    if not (target_surface or "").strip() or not (row_surface or "").strip():
        return False
    if "carpet" in target_surface.lower() or "carpet" in row_surface.lower():
        return "carpet" in target_surface.lower() and "carpet" in row_surface.lower()
    return normalize_surface(target_surface) == normalize_surface(row_surface)


def _exact_surface_match(target_surface: str, row_surface: str) -> bool:
    t_low = (target_surface or "").strip().lower()
    r_low = (row_surface or "").strip().lower()
    return bool(t_low and r_low and (t_low in r_low or r_low == t_low))


def _clean_winner_text(raw_text: str) -> str:
    no_brackets = re.sub(r"[\(\[].*?[\)\]]", "", raw_text or "")
    parts = _DEFEAT_SPLIT_RE.split(no_brackets, maxsplit=1)
    return re.sub(r"\s+", " ", parts[0]).strip()


def _extract_match_href(row_elem) -> str:
    links = row_elem.find_all("a")
    for link in links:
        href = link.get("href", "")
        if "/match/" in href:
            return href
    return links[-1].get("href", "") if links else ""


class H2HDataProcessor:
    """Parse les lignes HTML H2H sur MatchAnalysisData."""

    def __init__(self, data: BeautifulSoup, match: MatchAnalysisData) -> None:
        self.data = data
        self.match = match
        self.surface = match.surface
        self.player_a_name = match.player_a.name
        self.player_b_name = match.player_b.name
        self.stats = H2HStats(match.player_a.name, match.player_b.name)
        self.go_url = ""
        self.flag = 0
        self._has_exact_surface_url = False

    def process(self) -> None:
        """Exécute le comptage et le parsing des confrontations passées."""
        self._process_h2h_count()
        self._process_h2h_matches()
        self.match.h2h = self.stats.to_metrics()

    def process_h2h_data(self) -> None:
        """Alias rétrocompatible de process()."""
        self.process()

    def _process_h2h_count(self) -> None:
        if not self.data or not getattr(self.data, "text", None) or "series " not in self.data.text:
            self.match.h2h = H2HMetrics()
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
            self.match.h2h = H2HMetrics()

    @staticmethod
    def _parse_row_score(raw_score: str) -> str:
        clean_score = re.sub(r"[\(\[].*?[\)\]]", "", raw_score)
        res = clean_score.replace("ret.", " ").replace("w/o", "").strip()
        return res if res else "0-0 0-0"

    @classmethod
    def _extract_from_cells(
        cls, cells: List[str], player_a: str = "", player_b: str = ""
    ) -> Tuple[float, str, str, str]:
        date_ms = 0.0
        date_idx: Optional[int] = None
        for idx, txt in enumerate(cells):
            parsed = DateUtils.parse_date(txt)
            if parsed > 0.0:
                date_ms = parsed
                date_idx = idx
                break

        surface_m = ""
        surf_idx: Optional[int] = None
        for idx, txt in enumerate(cells):
            if idx == date_idx:
                continue
            surf_match = _SURFACE_RE.search(txt)
            if surf_match:
                surface_m = surf_match.group(0).strip()
                surf_idx = idx
                break

        score = "0-0 0-0"
        score_idx: Optional[int] = None
        for idx in range(len(cells) - 1, -1, -1):
            if idx in (date_idx, surf_idx):
                continue
            if _SCORE_RE.search(cells[idx]):
                score = cls._parse_row_score(cells[idx])
                score_idx = idx
                break

        winner = ""
        used = {date_idx, surf_idx, score_idx}
        for idx, txt in enumerate(cells):
            if idx in used or not txt:
                continue
            if _DEFEAT_SPLIT_RE.search(txt):
                winner = _clean_winner_text(txt)
                break

        if not winner and (player_a or player_b):
            for idx, txt in enumerate(cells):
                if idx in used or not txt:
                    continue
                cleaned = _clean_winner_text(txt)
                if _matches_player(cleaned, player_a) or _matches_player(cleaned, player_b):
                    winner = cleaned
                    break

        if not winner and len(cells) >= 3 and 2 not in used:
            winner = _clean_winner_text(cells[2])

        return date_ms, surface_m, winner, score

    @classmethod
    def _extract_match_details(
        cls, row_elem, player_a: str = "", player_b: str = ""
    ) -> Tuple[float, str, str, str]:
        """Extrait date, surface, vainqueur et score depuis une ligne <tr>."""
        tds = row_elem.find_all("td")
        if len(tds) >= 3:
            cells = [td.get_text(" ", strip=True) for td in tds]
            return cls._extract_from_cells(cells, player_a=player_a, player_b=player_b)

        lines = [line.strip() for line in row_elem.text.strip().split("\n") if line.strip()]
        tab_parts = row_elem.text.strip().split("\t")
        date_ms = DateUtils.parse_date(tab_parts[0].strip()) if tab_parts else 0.0
        surface_m = lines[5].split(",")[0].strip() if len(lines) > 5 else ""
        raw_winner = lines[7].strip() if len(lines) > 7 else ""
        winner = _clean_winner_text(raw_winner)
        raw_score = lines[9].strip() if len(lines) > 9 else ""
        return date_ms, surface_m, winner, cls._parse_row_score(raw_score)

    def _update_go_flag(self, row_elem, surface_m: str, winner: str) -> None:
        href = _extract_match_href(row_elem)
        if not href:
            return
        is_exact = _exact_surface_match(self.surface, surface_m)
        if is_exact and not self._has_exact_surface_url:
            self.go_url = href
            self.flag = 0 if _matches_player(winner, self.player_a_name) else 1
            self._has_exact_surface_url = True
        elif not self.go_url and _same_surface_bucket(self.surface, surface_m):
            self.go_url = href
            self.flag = 0 if _matches_player(winner, self.player_a_name) else 1

    def _find_h2h_container(self):
        if not self.data:
            return None
        container = self.data.find(class_="h2h-matches")
        if container:
            return container
        for table in self.data.find_all("table"):
            classes = " ".join(table.get("class") or []).lower()
            if "h2h" in classes:
                return table
        return None

    def _process_h2h_matches(self) -> None:
        h2h_elem = self._find_h2h_container()
        if not h2h_elem:
            logger.debug(
                "Tableau H2H introuvable dans le DOM pour %s vs %s",
                self.player_a_name,
                self.player_b_name,
            )
            return
        for row_elem in h2h_elem.find_all("tr"):
            if row_elem.find("th"):
                continue
            date_ms, surface_m, winner, score = self._extract_match_details(
                row_elem, player_a=self.player_a_name, player_b=self.player_b_name
            )
            if not winner:
                continue
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
