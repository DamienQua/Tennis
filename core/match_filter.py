"""Règles de filtrage des URLs d'aperçus de matchs."""

from datetime import datetime
from typing import Iterable, Union
from utils.helpers import canonicalize_match_url, extract_match_id


class MatchFilter:
    """Détermine si une URL de match doit être analysée."""

    SPECIAL_PLAYERS = ("fruhvirtova", "noskova", "efremova", "andreeva", "krueger")
    VALID_CIRCUITS = ("atp", "wta", "masters")
    EXCLUDED_PATTERNS = ("/q/", "tba-tba")

    @classmethod
    def is_valid_season(cls, match_url: str) -> bool:
        """Vérifie si l'URL correspond à la saison en cours ou suivante."""
        year = datetime.now().year
        return str(year) in match_url or str(year + 1) in match_url

    @classmethod
    def is_valid_circuit(cls, match_url: str) -> bool:
        """Vérifie si l'URL appartient aux circuits ATP, WTA ou Masters."""
        url_low = match_url.lower()
        return any(sub in url_low for sub in cls.VALID_CIRCUITS)

    @classmethod
    def is_special_case(cls, match_url: str) -> bool:
        """Identifie les joueuses suivies en exception."""
        url_low = match_url.lower()
        return any(name in url_low for name in cls.SPECIAL_PLAYERS)

    @staticmethod
    def _is_already_processed(
        url_canon: str, already_processed: Union[Iterable[str], str]
    ) -> bool:
        if not already_processed:
            return False
        match_id = extract_match_id(url_canon)

        if isinstance(already_processed, str):
            if url_canon in already_processed or canonicalize_match_url(already_processed) == url_canon:
                return True
            return bool(match_id and f"/match/{match_id}" in already_processed)

        for item in already_processed:
            item_canon = canonicalize_match_url(item)
            if item_canon == url_canon:
                return True
            if match_id and extract_match_id(item_canon) == match_id:
                return True
        return False

    @classmethod
    def should_process(
        cls, match_url: str, already_processed: Union[Iterable[str], str] = ""
    ) -> bool:
        """Applique les règles d'exclusion, de déduplication canonique et d'éligibilité."""
        url_clean = canonicalize_match_url(match_url)
        if any(pattern in url_clean for pattern in cls.EXCLUDED_PATTERNS):
            return False
        if cls._is_already_processed(url_clean, already_processed):
            return False
        if cls.is_valid_season(url_clean) and cls.is_valid_circuit(url_clean):
            return True
        return cls.is_special_case(url_clean)
