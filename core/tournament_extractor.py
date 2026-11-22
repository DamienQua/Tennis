"""Extraction des métadonnées du tournoi, de la surface, des classements et du statut."""

from datetime import datetime, timezone
import re
from typing import List, Optional, Sequence, Tuple
from bs4 import BeautifulSoup
import jaro
import numpy as np
from utils.helpers import parse_english_date

_SIGNED_NUM_RE = re.compile(r"([+\-]?\d+(?:\.\d+)?)")
_FINISHED_RE = re.compile(r"\b(?:def\.(?=\s|$)|defeated\b)", re.IGNORECASE)
_LIVE_MARKERS = ("in progress", "live now", "live score")
_ISO_UTC_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2})(?::\d{2})?\s*(?:Z|UTC|GMT)\b",
    re.IGNORECASE,
)
_EN_DATETIME_RE = re.compile(
    r"\b([A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4})\s*(?:at\s+|,\s*|\s+)(\d{1,2}:\d{2})\s*(?:GMT|UTC)\b",
    re.IGNORECASE,
)
_DMY_DATETIME_RE = re.compile(
    r"\b(\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4})\s*(?:at\s+|,\s*|\s+)(\d{1,2}:\d{2})\s*(?:GMT|UTC)\b",
    re.IGNORECASE,
)
_TIME_GMT_RE = re.compile(r"\b(\d{1,2}):(\d{2})\s*(?:GMT|UTC)\b", re.IGNORECASE)


def _normalize_minus(text: str) -> str:
    return (text or "").replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")


def _extract_signed_float(text: str) -> Optional[float]:
    cleaned = _normalize_minus(text).replace(",", ".")
    match = _SIGNED_NUM_RE.search(cleaned)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_header_text_without_h2h(soup: Optional[BeautifulSoup]) -> str:
    if not soup:
        return ""
    clone = BeautifulSoup(str(soup), "lxml")
    for h2h_block in clone.find_all(class_="h2h-matches"):
        h2h_block.decompose()
    header = clone.find(class_="match-preview-header") or clone.find("h1")
    if header and header.parent:
        return header.parent.get_text(" ", strip=True)
    return clone.get_text(" ", strip=True)[:2500]


def _parse_scheduled_utc(text: str, now_utc: datetime) -> Optional[datetime]:
    """Extrait l'horaire programmé UTC/GMT depuis l'en-tête TennisInsight s'il est présent."""
    iso_m = _ISO_UTC_RE.search(text)
    if iso_m:
        try:
            dt = datetime.strptime(f"{iso_m.group(1)} {iso_m.group(2)}", "%Y-%m-%d %H:%M")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    en_m = _EN_DATETIME_RE.search(text)
    if en_m:
        try:
            base = parse_english_date(en_m.group(1))
            hour, minute = [int(x) for x in en_m.group(2).split(":")]
            return base.replace(hour=hour, minute=minute, tzinfo=timezone.utc)
        except ValueError:
            pass

    dmy_m = _DMY_DATETIME_RE.search(text)
    if dmy_m:
        parts = dmy_m.group(1).split()
        if len(parts) == 3:
            try:
                base = parse_english_date(f"{parts[1]} {parts[0]} {parts[2]}")
                hour, minute = [int(x) for x in dmy_m.group(2).split(":")]
                return base.replace(hour=hour, minute=minute, tzinfo=timezone.utc)
            except ValueError:
                pass

    time_m = _TIME_GMT_RE.search(text)
    if time_m:
        hour, minute = int(time_m.group(1)), int(time_m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return now_utc.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return None


class TournamentExtractor:
    """Extrait le tournoi, la surface, le classement mondial, le favori et le statut."""

    @staticmethod
    def extract_tournament_slug(match_url: str) -> str:
        """Extrait le slug du tournoi depuis l'URL du match."""
        found = re.search(r"/\d{4}-([^/]+)/", match_url)
        if found:
            return found.group(1)
        parts = [part for part in match_url.split("/") if part]
        return parts[-2] if len(parts) >= 2 else match_url

    @staticmethod
    def _infer_surface_from_text(text: str) -> str:
        low = text.lower()
        if "indoor" in low:
            return "Indoor Hard"
        if "grass" in low:
            return "Grass"
        if "clay" in low:
            return "Clay"
        return "Hard"

    @classmethod
    def determine_tournament_and_surface(
        cls, match_url: str, tournaments: Sequence[str]
    ) -> Tuple[str, str]:
        """Détermine le nom du tournoi et la surface."""
        slug = cls.extract_tournament_slug(match_url)
        if tournaments is not None and len(tournaments) > 0:
            t_list = list(tournaments)
            scores = np.array(
                [jaro.jaro_winkler_metric(slug, t.split(" (")[0].lower()) for t in t_list],
                dtype=float,
            )
            tour_str = t_list[int(scores.argmax())]
            tour = tour_str.split(" (")[0]
            if "- " in tour_str:
                surface = tour_str.split("- ")[1].split(" Court")[0].strip()
            else:
                surface = cls._infer_surface_from_text(tour_str)
            return tour, surface
        clean_tour = slug.replace("-", " ").title()
        return clean_tour, cls._infer_surface_from_text(clean_tour)

    @staticmethod
    def parse_player_rankings(data: BeautifulSoup) -> List[int]:
        """Extrait les classements ATP/WTA des deux joueurs."""
        rankings: List[int] = []
        clean_txt = data.text.replace("Unknown", "1000")
        for idx in range(2):
            try:
                ranking = int(clean_txt.split("(HI")[idx].split("\n")[-1].strip())
            except (ValueError, IndexError, AttributeError):
                ranking = 1000
            rankings.append(ranking)
        return rankings

    @staticmethod
    def _compare_lower_is_fav(left_val: float, right_val: float) -> List[int]:
        if left_val < right_val:
            return [1, 0]
        if left_val > right_val:
            return [0, 1]
        return [0, 0]

    @classmethod
    def who_is_favorite(
        cls,
        data: Optional[BeautifulSoup],
        book_odds: Optional[Tuple[float, float]] = None,
    ) -> List[int]:
        """Identifie le favori via cotes moneyline validées, sinon depuis mp_bio (handicap/cote)."""
        if book_odds and len(book_odds) == 2:
            o_a, o_b = float(book_odds[0] or 0.0), float(book_odds[1] or 0.0)
            if o_a > 1.01 and o_b > 1.01 and o_a != o_b:
                return cls._compare_lower_is_fav(o_a, o_b)

        try:
            left_box = data.find(class_="mp_bio_left") if data else None
            right_box = data.find(class_="mp_bio_right") if data else None
            if not left_box or not right_box:
                return [0, 0]
            left_items = [li.get_text(" ", strip=True) for li in left_box.find_all("li")]
            right_items = [li.get_text(" ", strip=True) for li in right_box.find_all("li")]
            if not left_items or not right_items:
                return [0, 0]

            # 1. Priorité aux lignes explicitement marquées comme cotes moneyline ($ ou 'odds')
            for l_txt, r_txt in zip(left_items, right_items):
                l_low, r_low = l_txt.lower(), r_txt.lower()
                is_odds = ("$" in l_txt and "$" in r_txt) or (
                    ("odds" in l_low or "moneyline" in l_low)
                    and ("odds" in r_low or "moneyline" in r_low)
                )
                if is_odds:
                    l_val = _extract_signed_float(l_txt)
                    r_val = _extract_signed_float(r_txt)
                    if l_val is not None and r_val is not None and l_val > 1.0 and r_val > 1.0:
                        return cls._compare_lower_is_fav(l_val, r_val)

            # 2. Dernier <li> : handicap de sets (+1.5 vs -1.5), cotes décimales, ou probabilité (%)
            l_last, r_last = left_items[-1], right_items[-1]
            l_val = _extract_signed_float(l_last)
            r_val = _extract_signed_float(r_last)
            if l_val is None or r_val is None or l_val == r_val:
                return [0, 0]

            if "%" in l_last and "%" in r_last:
                return [1, 0] if l_val > r_val else [0, 1]

            # Pour handicap (+1.5 vs -1.5), cotes décimales (2.72 vs 1.50) et US (+170 vs -200) :
            # la valeur numérique la plus basse désigne le favori.
            return cls._compare_lower_is_fav(l_val, r_val)
        except (ValueError, IndexError, AttributeError):
            return [0, 0]

    @staticmethod
    def check_match_prematch_status(
        soup_main: Optional[BeautifulSoup],
        soup_overview: Optional[BeautifulSoup],
        now_utc: Optional[datetime] = None,
    ) -> Tuple[bool, str]:
        """Vérifie que la rencontre n'est ni terminée, ni en cours, ni après l'horaire GMT annoncé."""
        current_utc = now_utc or datetime.now(timezone.utc)
        for soup in (soup_main, soup_overview):
            header_text = _extract_header_text_without_h2h(soup)
            if not header_text:
                continue
            if _FINISHED_RE.search(header_text):
                return False, "match_finished"
            low = header_text.lower()
            if any(marker in low for marker in _LIVE_MARKERS):
                return False, "match_live"
            scheduled = _parse_scheduled_utc(header_text, current_utc)
            if scheduled is not None and current_utc >= scheduled:
                return False, f"match_started ({scheduled.strftime('%Y-%m-%d %H:%M UTC')})"
        return True, "prematch"


extract_tournament_slug = TournamentExtractor.extract_tournament_slug
determine_tournament_and_surface = TournamentExtractor.determine_tournament_and_surface
parse_player_rankings = TournamentExtractor.parse_player_rankings
who_is_favorite = TournamentExtractor.who_is_favorite
check_match_prematch_status = TournamentExtractor.check_match_prematch_status
