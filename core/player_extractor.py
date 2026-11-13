"""Extraction des identifiants et noms normalisés des joueurs."""

import re
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup


class PlayerExtractor:
    """Extrait les IDs et noms propres des joueurs depuis la page de preview."""

    PLAYER_ALIASES = {
        "Cori Gauff": "Coco Gauff",
    }

    @staticmethod
    def _ids_from_soup(soup_abc: Optional[BeautifulSoup]) -> List[str]:
        if not soup_abc:
            return []
        seen: List[str] = []
        for link_elem in soup_abc.find_all("a"):
            href = link_elem.get("href", "")
            if "/player/?playerid=" in href and "General Comments" not in link_elem.text:
                match_obj = re.search(r"playerid=(\d+)", href)
                if match_obj and match_obj.group(1) not in seen:
                    seen.append(match_obj.group(1))
        return seen

    @staticmethod
    def _ids_from_regex(html_text: str) -> List[str]:
        raw = re.findall(r"/player/\?playerid=(\d+)", html_text)
        if len(raw) < 2:
            raw = re.findall(r"playerid=(\d+)", html_text)
        seen: List[str] = []
        for pid in raw:
            if pid not in seen:
                seen.append(pid)
        return seen

    @classmethod
    def extract_player_ids(
        cls, html_text: str, soup_abc: Optional[BeautifulSoup] = None
    ) -> Tuple[str, str]:
        """Extrait les identifiants uniques des joueurs A et B."""
        ids = cls._ids_from_soup(soup_abc)
        if len(ids) < 2 and isinstance(html_text, str):
            ids = cls._ids_from_regex(html_text)
        player_a_id = ids[0] if len(ids) > 0 else ""
        player_b_id = ids[1] if len(ids) > 1 else ""
        return player_a_id, player_b_id

    @classmethod
    def clean_player_name(cls, name: str) -> str:
        """Nettoie les têtes de série, suffixes et alias connus."""
        cleaned = re.sub(r"^\s*[\(\[][A-Za-z0-9/]+[\)\]]\s*", "", name.strip())
        cleaned = cleaned.replace("-Vinolas", "").replace(" Vitus Nodskov", "").strip()
        return cls.PLAYER_ALIASES.get(cleaned, cleaned)

    @classmethod
    def _names_from_title(cls, soup_abc: BeautifulSoup) -> Optional[Tuple[str, str]]:
        titles = soup_abc.find_all(class_="profile-title")
        if len(titles) >= 2:
            player_a = cls.clean_player_name(titles[0].text)
            player_b = cls.clean_player_name(titles[1].text)
            if player_a and player_b:
                return player_a, player_b
        return None

    @classmethod
    def _names_from_links(cls, soup_abc: BeautifulSoup) -> Optional[Tuple[str, str]]:
        players: List[str] = []
        seen_ids = set()
        for link_elem in soup_abc.find_all("a"):
            href = link_elem.get("href", "")
            match_id = re.search(r"playerid=(\d+)", href)
            text = link_elem.text.strip()
            if match_id and text and "General Comments" not in text:
                pid = match_id.group(1)
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    players.append(cls.clean_player_name(text))
        return (players[0], players[1]) if len(players) >= 2 else None

    @classmethod
    def _names_from_overview(cls, data_text: str) -> Optional[Tuple[str, str]]:
        for_parts = data_text.split("for ")
        if len(for_parts) >= 3:
            player_a = cls.clean_player_name(for_parts[1].split("\n")[0])
            player_b = cls.clean_player_name(for_parts[2].split("\n")[0])
            if player_a and player_b:
                return player_a, player_b
        return None

    @staticmethod
    def _names_from_slug(match_url: str) -> Optional[Tuple[str, str]]:
        parts = [part for part in match_url.split("/") if part]
        match_slug = parts[-1] if parts else ""
        if "-vs-" in match_slug:
            slug_parts = match_slug.split("-vs-")
            if len(slug_parts) >= 2:
                return (
                    slug_parts[0].replace("-", " ").title(),
                    slug_parts[1].replace("-", " ").title(),
                )
        return None

    @classmethod
    def extract_player_names(
        cls, soup_abc: BeautifulSoup, match_url: str, data_text: str = ""
    ) -> Tuple[str, str]:
        """Extrait les noms des joueurs avec chaîne de repli."""
        return (
            cls._names_from_title(soup_abc)
            or cls._names_from_links(soup_abc)
            or cls._names_from_overview(data_text)
            or cls._names_from_slug(match_url)
            or ("Player A", "Player B")
        )


clean_player_name = PlayerExtractor.clean_player_name
extract_player_ids = PlayerExtractor.extract_player_ids
extract_player_names = PlayerExtractor.extract_player_names