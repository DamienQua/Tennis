"""Adaptateurs du modèle probabiliste commun aux analyses et aux backtests."""

from typing import Any
from analysis.probability_model import build_features, load_model, model_odds
from core.models import MatchAnalysisData


def compare_players(match_data: Any) -> Any:
    """Calcule des cotes équitables 1/p ; conserve les autres stats pour les rapports."""
    model = load_model()
    if isinstance(match_data, MatchAnalysisData):
        pa, pb = match_data.player_a, match_data.player_b
        try:
            features = build_features(
                pa.ranking, pb.ranking, pa.win_pct_1y, pb.win_pct_1y,
                pa.win_pct_career_surface, pb.win_pct_career_surface, pa.elo, pb.elo,
            )
            pa.model_odds, pb.model_odds = model_odds(features, match_data.surface, model)
        except (ValueError, TypeError):
            # Une donnée absente ne doit jamais produire un signal de pari.
            pa.model_odds = pb.model_odds = 0.0
        return match_data

    # Le format historique conserve les ELO aux indices 40 et 41.
    try:
        features = build_features(
            match_data[4], match_data[5], match_data[16], match_data[27],
            match_data[19], match_data[30], match_data[40], match_data[41],
        )
        match_data[36], match_data[37] = model_odds(features, str(match_data[1]), model)
    except (ValueError, TypeError, IndexError):
        match_data[36], match_data[37] = 0.0, 0.0
    return match_data
