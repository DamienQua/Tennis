"""
Module for extracting player identifiers and clean names from match HTML and metadata.
"""

import re
from typing import Optional, Tuple


class PlayerExtractor:
    """Extracts player identifiers and normalized names from match preview data."""

    @staticmethod
    def _ids_from_soup(soup_abc):
        if not soup_abc:
            return []
        seen = []
        for link_elem in soup_abc.find_all('a'):
            href = link_elem.get('href', '')
            if '/player/?playerid=' in href:
                match_obj = re.search(r'playerid=(\d+)', href)
                valid_link = (
                    match_obj
                    and match_obj.group(1) not in seen
                    and 'General Comments' not in link_elem.text
                )
                if valid_link:
                    seen.append(match_obj.group(1))
        return seen

    @staticmethod
    def _ids_from_regex(abc):
        raw = re.findall(r'/player/\?playerid=(\d+)', abc)
        if len(raw) < 2:
            raw = re.findall(r'playerid=(\d+)', abc)
        seen = []
        for pid in raw:
            if pid not in seen:
                seen.append(pid)
        return seen

    @classmethod
    def extract_player_ids(cls, abc: str, soup_abc=None) -> Tuple[str, str]:
        """Extracts unique player IDs for player A and player B."""
        ids = cls._ids_from_soup(soup_abc)
        if len(ids) < 2 and isinstance(abc, str):
            ids = cls._ids_from_regex(abc)
        player_a_id = ids[0] if len(ids) > 0 else ""
        player_b_id = ids[1] if len(ids) > 1 else ""
        return player_a_id, player_b_id

    @staticmethod
    def clean_player_name(name: str) -> str:
        """Cleans player name string by removing unwanted suffixes."""
        cleaned = re.sub(r'^\s*[\(\[][A-Za-z0-9/]+[\)\]]\s*', '', name.strip())
        cleaned = cleaned.replace("-Vinolas", "").replace(" Vitus Nodskov", "").strip()
        if cleaned == "Cori Gauff":
            return "Coco Gauff"
        return cleaned

    @classmethod
    def _names_from_title(cls, soup_abc) -> Optional[Tuple[str, str]]:
        titles = soup_abc.find_all(class_="profile-title")
        if len(titles) >= 2:
            player_a = cls.clean_player_name(titles[0].text)
            player_b = cls.clean_player_name(titles[1].text)
            if player_a and player_b:
                return player_a, player_b
        return None

    @classmethod
    def _names_from_links(cls, soup_abc) -> Optional[Tuple[str, str]]:
        players = []
        seen_ids = set()
        for link_elem in soup_abc.find_all('a'):
            href = link_elem.get('href', '')
            if '/player/?playerid=' in href:
                pid = href.split('playerid=')[-1]
                text = link_elem.text.strip()
                if pid not in seen_ids and text and 'General Comments' not in text:
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
        parts = [part for part in match_url.split('/') if part]
        match_slug = parts[-1] if parts else ""
        if '-vs-' in match_slug:
            slug_parts = match_slug.split('-vs-')
            if len(slug_parts) >= 2:
                name_a = slug_parts[0].replace('-', ' ').title()
                name_b = slug_parts[1].replace('-', ' ').title()
                return name_a, name_b
        return None

    @classmethod
    def extract_player_names(
            cls, soup_abc, match_url: str, data_text: str = ""
    ) -> Tuple[str, str]:
        """Extracts player names from title, links, overview, or URL slug."""
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
