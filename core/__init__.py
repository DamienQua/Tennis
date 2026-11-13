"""Module core : modèles, base de données, filtrage, extraction et analyse."""

import importlib
from typing import Any

_LAZY_EXPORTS = {
    "analyze_match": ("core.analyze_match", "analyze_match"),
    "get_session_bets": ("core.analyze_match", "get_session_bets"),
    "clear_session_bets": ("core.analyze_match", "clear_session_bets"),
    "TennisDatabase": ("core.database", "TennisDatabase"),
    "MatchFilter": ("core.match_filter", "MatchFilter"),
    "MatchRepository": ("core.match_repository", "MatchRepository"),
    "MatchAnalysisData": ("core.models", "MatchAnalysisData"),
    "PlayerStats": ("core.models", "PlayerStats"),
    "H2HMetrics": ("core.models", "H2HMetrics"),
    "ConfidenceMetrics": ("core.models", "ConfidenceMetrics"),
    "PlayerExtractor": ("core.player_extractor", "PlayerExtractor"),
    "clean_player_name": ("core.player_extractor", "clean_player_name"),
    "extract_player_ids": ("core.player_extractor", "extract_player_ids"),
    "extract_player_names": ("core.player_extractor", "extract_player_names"),
    "TournamentExtractor": ("core.tournament_extractor", "TournamentExtractor"),
    "determine_tournament_and_surface": (
        "core.tournament_extractor",
        "determine_tournament_and_surface",
    ),
    "extract_tournament_slug": ("core.tournament_extractor", "extract_tournament_slug"),
    "parse_player_rankings": ("core.tournament_extractor", "parse_player_rankings"),
    "who_is_favorite": ("core.tournament_extractor", "who_is_favorite"),
}

__all__ = list(_LAZY_EXPORTS.keys())


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module_path, attr_name = _LAZY_EXPORTS[name]
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module 'core' has no attribute '{name}'")