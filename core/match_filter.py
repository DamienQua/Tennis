"""Règles de filtrage des URLs d'aperçus de matchs."""

from datetime import datetime
from typing import Set


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

    @classmethod
    def should_process(cls, match_url: str, already_processed: Set[str]) -> bool:
        """Applique les règles d'exclusion, de déduplication et d'éligibilité."""
        url_clean = match_url.strip()
        if any(pattern in url_clean for pattern in cls.EXCLUDED_PATTERNS):
            return False
        if url_clean in already_processed:
            return False
        if cls.is_valid_season(url_clean) and cls.is_valid_circuit(url_clean):
            return True
        return cls.is_special_case(url_clean)