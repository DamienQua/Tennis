"""Modèle logistique unique pour production, calibration et simulation historique.

Le modèle de référence est heuristique, non calibré. Les anciens poids de scores
ne sont pas des coefficients logistiques et sont volontairement incompatibles.
Les cotes retournées sont équitables (1/p), sans marge artificielle ni arrondi.
"""

from datetime import date
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

import numpy as np

SCHEMA_VERSION = 1
MODEL_TYPE = "logistic_difference"
FEATURE_NAMES = ("rank_difference", "form_12m_difference", "surface_career_difference", "elo_difference")
BASELINE_WEIGHTS = (0.8, 0.8, 1.2, 1.0)
DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[1] / "config" / "calibrated_weights.json"


def surface_bucket(surface: str) -> str:
    value = surface.strip().lower()
    return "clay" if "clay" in value else ("grass" if "grass" in value else "hard")


def baseline_model() -> dict:
    """Retourne une configuration indépendante, explicitement non calibrée."""
    return {
        "schema_version": SCHEMA_VERSION,
        "model_type": MODEL_TYPE,
        "feature_names": list(FEATURE_NAMES),
        "description": "Heuristic baseline; not empirically calibrated or validated.",
        "surfaces": {
            surface: {"status": "baseline", "weights": list(BASELINE_WEIGHTS)}
            for surface in ("hard", "clay", "grass")
        },
    }


def build_features(
    rank_a: float, rank_b: float, form_a: float, form_b: float,
    surface_a: float, surface_b: float, elo_a: float, elo_b: float,
) -> Tuple[float, float, float, float]:
    """Différences symétriques : rang relatif, taux /100 et ELO /400."""
    values = np.asarray([rank_a, rank_b, form_a, form_b, surface_a, surface_b, elo_a, elo_b], dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Model inputs must be finite")
    ra, rb, fa, fb, sa, sb, ea, eb = values
    if min(ra, rb, ea, eb) <= 0 or np.any(values[2:6] < 0) or np.any(values[2:6] > 100):
        raise ValueError("Missing or out-of-range model inputs")
    return float((rb - ra) / max(ra, rb)), float((fa - fb) / 100), float((sa - sb) / 100), float((ea - eb) / 400)


def predict_probabilities(features: Any, weights: Sequence[float] = BASELINE_WEIGHTS) -> Any:
    """Même fonction pour un vecteur de production ou une matrice d'entraînement."""
    matrix = np.asarray(features, dtype=float)
    coefficients = np.asarray(weights, dtype=float)
    if coefficients.shape != (4,) or matrix.ndim not in (1, 2) or matrix.shape[-1] != 4:
        raise ValueError("Expected four model features and coefficients")
    if not np.isfinite(matrix).all() or not np.isfinite(coefficients).all():
        raise ValueError("Model features and coefficients must be finite")
    result = 1.0 / (1.0 + np.exp(-np.clip(matrix @ coefficients, -20.0, 20.0)))
    return float(result) if matrix.ndim == 1 else result


def load_model(path: Optional[Any] = None) -> dict:
    """Ignore les anciens formats, les coefficients non finis et la validation absente."""
    try:
        with open(path or DEFAULT_MODEL_PATH, encoding="utf-8") as stream:
            model = json.load(stream)
        if (model.get("schema_version") != SCHEMA_VERSION or model.get("model_type") != MODEL_TYPE
                or model.get("feature_names") != list(FEATURE_NAMES)):
            return baseline_model()
        for surface in ("hard", "clay", "grass"):
            entry = model["surfaces"][surface]
            weights = np.asarray(entry["weights"], dtype=float)
            if weights.shape != (4,) or not np.isfinite(weights).all() or np.any(weights < 0):
                return baseline_model()
            if entry["status"] == "validated":
                train_end = date.fromisoformat(entry["trained_through"])
                validation_start = date.fromisoformat(entry["validation_from"])
                validation_end = date.fromisoformat(entry["validated_through"])
                if not train_end < validation_start <= validation_end:
                    return baseline_model()
                metrics = entry["validation_metrics"]
                scores = np.asarray([
                    metrics["baseline_brier"], metrics["candidate_brier"],
                    metrics["baseline_log_loss"], metrics["candidate_log_loss"],
                ], dtype=float)
                counts = (entry["training_samples"], entry["validation_samples"])
                if (not np.isfinite(scores).all() or np.any(scores < 0)
                        or np.any(scores[:2] > 1)
                        or not scores[1] < scores[0] or scores[3] > scores[2]
                        or any(type(count) is not int for count in counts)
                        or counts[0] < 20 or counts[1] < 10):
                    return baseline_model()
            elif entry["status"] != "baseline" or not np.array_equal(weights, BASELINE_WEIGHTS):
                return baseline_model()
        return model
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return baseline_model()


def get_weights(surface: str, model: Optional[Mapping] = None, as_of: Optional[Any] = None) -> Sequence[float]:
    """Un modèle validé n'est disponible qu'après la dernière date de validation."""
    entry = (model or baseline_model())["surfaces"][surface_bucket(surface)]
    if entry.get("status") == "validated":
        try:
            prediction_date = date.today() if as_of is None else date.fromisoformat(str(as_of)[:10])
            validation_end = date.fromisoformat(entry["validated_through"])
        except (ValueError, TypeError, KeyError):
            return BASELINE_WEIGHTS
        if prediction_date <= validation_end:
            return BASELINE_WEIGHTS
    return entry["weights"]


def model_odds(features: Sequence[float], surface: str, model: Optional[Mapping] = None,
               as_of: Optional[Any] = None) -> Tuple[float, float]:
    probability = predict_probabilities(features, get_weights(surface, model, as_of))
    return 1.0 / probability, 1.0 / (1.0 - probability)
