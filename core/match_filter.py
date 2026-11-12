"""
Module providing filtering rules for tennis match preview URLs.

Encapsulates criteria for:
- Season/Year validation
- Tournament circuit validation (ATP, WTA, Masters)
- Exclusion patterns (qualifiers, TBA matches)
- Special player exceptions
"""

from datetime import datetime

class MatchFilter:
    """Filter to determine whether a tennis match preview should be processed."""

    SPECIAL_PLAYERS = ("fruhvirtova", "noskova", "efremova", "andreeva", "krueger")
    VALID_CIRCUITS = ("atp", "wta", "masters")
    EXCLUDED_PATTERNS = ("/q/", "tba-tba")

    @classmethod
    def is_valid_season(cls, match_url):
        year = str(datetime.now().year)
        return year in match_url or str(int(year) + 1) in match_url

    @classmethod
    def is_valid_circuit(cls, match_url):
        return any(sub in match_url for sub in cls.VALID_CIRCUITS)

    @classmethod
    def is_special_case(cls, match_url):
        return any(name in match_url for name in cls.SPECIAL_PLAYERS)

    @classmethod
    def should_process(cls, match_url, already_processed=""):
        if any(pattern in match_url for pattern in cls.EXCLUDED_PATTERNS):
            return False

        if match_url in already_processed:
            return False

        if cls.is_valid_season(match_url) and cls.is_valid_circuit(match_url):
            return True

        return cls.is_special_case(match_url)
