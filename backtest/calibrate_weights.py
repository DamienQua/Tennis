"""Fit the production model on earlier dates and promote on a later holdout only."""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from analysis.probability_model import (
    BASELINE_WEIGHTS, baseline_model, build_features, predict_probabilities, surface_bucket,
)
from backtest.point_in_time_stats import PointInTimeStats, completed_matches

DEFAULT_WEIGHTS_PATH = "config/calibrated_weights.json"
MIN_TRAINING_SAMPLES = 20
MIN_VALIDATION_SAMPLES = 10


def brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Mean squared error of probabilities against observed outcomes."""
    return float(np.mean((y_prob - y_true) ** 2)) if len(y_true) else 0.25


def log_loss(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Binary log loss; clipping only guards numerical underflow."""
    if not len(y_true):
        return float(np.log(2.0))
    probs = np.clip(y_prob, 1e-7, 1.0 - 1e-7)
    return float(-np.mean(y_true * np.log(probs) + (1.0 - y_true) * np.log(1.0 - probs)))


def _fit_logistic_weights(
    features: np.ndarray, labels: np.ndarray, l2_reg: float = 0.05,
) -> np.ndarray:
    """Fit exact coefficients for the same function used for live predictions."""
    def objective(weights: np.ndarray) -> float:
        probabilities = predict_probabilities(features, weights)
        return log_loss(labels, probabilities) + l2_reg * float(np.sum(weights ** 2))

    result = minimize(
        objective, np.asarray(BASELINE_WEIGHTS), method="L-BFGS-B", bounds=[(0.0, 10.0)] * 4,
    )
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError("Logistic optimizer failed to converge")
    return result.x


def _extract_surface_samples(df: pd.DataFrame, stats_engine: PointInTimeStats) -> pd.DataFrame:
    """Preserve dates alongside features so the split cannot mix the same day."""
    samples = []
    for index, row in completed_matches(df).iterrows():
        winner, loser = row["Winner"], row["Loser"]
        played, surface = row["Date"], str(row.get("Surface", "Hard"))
        form_w, surf_w, count_w = stats_engine.get_player_stats_before(winner, played, surface)
        form_l, surf_l, count_l = stats_engine.get_player_stats_before(loser, played, surface)
        if min(count_w, count_l) < 3:
            continue
        try:
            features = build_features(
                row.get("WRank"), row.get("LRank"), form_w, form_l, surf_w, surf_l,
                stats_engine.get_player_elo_before(winner, played, surface),
                stats_engine.get_player_elo_before(loser, played, surface),
            )
        except (TypeError, ValueError):
            continue
        # No intercept: opposite orientations are mathematically complementary.
        sign = 1.0 if index % 2 == 0 else -1.0
        samples.append({
            "date": played, "surface": surface_bucket(surface),
            "features": [sign * value for value in features], "label": float(sign > 0),
        })
    return pd.DataFrame(samples, columns=["date", "surface", "features", "label"])


def _validation_boundary(samples: pd.DataFrame, validation_start: Optional[Any]) -> Optional[pd.Timestamp]:
    if samples.empty:
        return None
    if validation_start is not None:
        return pd.Timestamp(validation_start).normalize()
    dates = sorted(samples["date"].unique())
    years = sorted({pd.Timestamp(value).year for value in dates})
    if len(years) > 1:
        # Reserve the newest season when multiple seasons are available.
        return pd.Timestamp(year=years[-1], month=1, day=1)
    if len(dates) < 2:
        return None
    return pd.Timestamp(dates[min(len(dates) - 1, int(len(dates) * 0.8))])


def _matrix(samples: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    return np.asarray(samples["features"].tolist(), dtype=float), samples["label"].to_numpy(dtype=float)


def calibrate_from_dataframe(
    df: pd.DataFrame, output_path: str = DEFAULT_WEIGHTS_PATH, *,
    validation_start: Optional[Any] = None,
) -> Dict[str, Any]:
    """Keep a baseline unless a disjoint later holdout improves Brier and log loss."""
    frame = completed_matches(df)
    groups = frame.groupby("Circuit") if "Circuit" in frame else [(None, frame)]
    sample_frames = [_extract_surface_samples(group, PointInTimeStats(group)) for _, group in groups]
    samples = pd.concat(sample_frames, ignore_index=True) if sample_frames else pd.DataFrame()
    boundary = _validation_boundary(samples, validation_start)
    model = baseline_model()
    model["selection_policy"] = "Later holdout: Brier strictly lower, log loss no higher than baseline."

    for surface, entry in model["surfaces"].items():
        selected = samples[samples["surface"] == surface] if not samples.empty else samples
        training = selected[selected["date"] < boundary] if boundary is not None else selected.iloc[:0]
        validation = selected[selected["date"] >= boundary] if boundary is not None else selected.iloc[:0]
        entry.update(training_samples=len(training), validation_samples=len(validation))
        if len(training) < MIN_TRAINING_SAMPLES or len(validation) < MIN_VALIDATION_SAMPLES:
            entry["reason"] = "Insufficient disjoint training or validation samples"
            continue
        entry.update(
            trained_through=training["date"].max().date().isoformat(),
            validation_from=validation["date"].min().date().isoformat(),
            validated_through=validation["date"].max().date().isoformat(),
        )
        train_x, train_y = _matrix(training)
        val_x, val_y = _matrix(validation)
        try:
            coefficients = _fit_logistic_weights(train_x, train_y)
        except ValueError:
            entry["reason"] = "Optimizer failed; baseline retained"
            continue
        baseline_prob = predict_probabilities(val_x, BASELINE_WEIGHTS)
        candidate_prob = predict_probabilities(val_x, coefficients)
        metrics = {
            "baseline_brier": brier_score(val_y, baseline_prob),
            "candidate_brier": brier_score(val_y, candidate_prob),
            "baseline_log_loss": log_loss(val_y, baseline_prob),
            "candidate_log_loss": log_loss(val_y, candidate_prob),
        }
        entry["validation_metrics"] = metrics
        if (metrics["candidate_brier"] < metrics["baseline_brier"]
                and metrics["candidate_log_loss"] <= metrics["baseline_log_loss"]):
            entry.update(status="validated", weights=coefficients.tolist())
        else:
            entry.update(reason="Candidate did not improve the later holdout", candidate_weights=coefficients.tolist())

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return model


def calibrate_from_archives(
    data_dir: str = "backtest/data", output_path: str = DEFAULT_WEIGHTS_PATH,
    *, validation_start: Optional[Any] = None,
) -> Dict[str, Any]:
    """Read local yearly archives; ATP and WTA histories stay separate."""
    frames = []
    for circuit in ("atp", "wta"):
        for path in sorted(Path(data_dir).glob(f"{circuit}_[0-9][0-9][0-9][0-9].xlsx")):
            frames.append(pd.read_excel(path).assign(Circuit=circuit))
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return calibrate_from_dataframe(combined, output_path, validation_start=validation_start)


if __name__ == "__main__":
    print(json.dumps(calibrate_from_archives(), indent=2))
