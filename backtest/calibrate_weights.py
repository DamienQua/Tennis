"""Calibration empirique des poids du modèle par surface (Log-Loss & Brier Score)."""

import json
import os
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from backtest.point_in_time_stats import PointInTimeStats

DEFAULT_WEIGHTS_PATH = "config/calibrated_weights.json"

DEFAULT_SURFACE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "hard": {"rank": 5.0, "form": 20.0, "surface": 30.0, "elo": 0.15, "trj": 0.90},
    "clay": {"rank": 5.0, "form": 20.0, "surface": 35.0, "elo": 0.15, "trj": 0.90},
    "grass": {"rank": 5.0, "form": 18.0, "surface": 32.0, "elo": 0.18, "trj": 0.90},
}


def _surface_bucket(surface: str) -> str:
    s_low = surface.strip().lower()
    if "clay" in s_low:
        return "clay"
    if "grass" in s_low:
        return "grass"
    return "hard"


def _sigmoid(z: np.ndarray) -> np.ndarray:
    clipped = np.clip(z, -20.0, 20.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Calcule le Brier Score (plus bas = meilleure calibration probabiliste)."""
    return float(np.mean((y_prob - y_true) ** 2)) if len(y_true) > 0 else 0.25


def log_loss(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Calcule la Log-Loss binaire."""
    if len(y_true) == 0:
        return 0.693
    eps = 1e-7
    probs = np.clip(y_prob, eps, 1.0 - eps)
    return float(-np.mean(y_true * np.log(probs) + (1.0 - y_true) * np.log(1.0 - probs)))


def _fit_logistic_weights(
    features: np.ndarray, labels: np.ndarray, l2_reg: float = 0.05
) -> Tuple[np.ndarray, float, float]:
    """Optimise les poids [rank, form, surface, elo] par minimisation de la Log-Loss."""
    init_w = np.array([0.8, 0.8, 1.2, 1.0], dtype=float)
    init_probs = _sigmoid(features @ init_w)
    brier_before = brier_score(labels, init_probs)

    def _objective(weights: np.ndarray) -> float:
        probs = _sigmoid(features @ weights)
        return log_loss(labels, probs) + l2_reg * float(np.sum(weights ** 2))

    res = minimize(
        _objective,
        init_w,
        method="L-BFGS-B",
        bounds=[(0.0, 10.0), (0.0, 10.0), (0.0, 10.0), (0.0, 10.0)],
    )
    opt_w = res.x
    brier_after = brier_score(labels, _sigmoid(features @ opt_w))
    return opt_w, brier_before, brier_after


def _extract_surface_samples(
    df: pd.DataFrame, stats_engine: PointInTimeStats
) -> Dict[str, Tuple[List[List[float]], List[float]]]:
    """Construit les vecteurs symétriques (X, y) sans look-ahead bias par surface."""
    buckets: Dict[str, Tuple[List[List[float]], List[float]]] = {
        "hard": ([], []),
        "clay": ([], []),
        "grass": ([], []),
    }
    completed = df[df["Comment"] == "Completed"] if "Comment" in df.columns else df

    for idx, row in completed.iterrows():
        p_w, p_l = str(row["Winner"]), str(row["Loser"])
        m_date = pd.to_datetime(row["Date"])
        surf = str(row.get("Surface", "Hard"))
        bucket = _surface_bucket(surf)

        form_w, surf_w, cnt_w = stats_engine.get_player_stats_before(p_w, m_date, surf)
        form_l, surf_l, cnt_l = stats_engine.get_player_stats_before(p_l, m_date, surf)
        if cnt_w < 3 or cnt_l < 3:
            continue

        elo_w = stats_engine.get_player_elo_before(p_w, m_date, surf)
        elo_l = stats_engine.get_player_elo_before(p_l, m_date, surf)
        r_w = float(row.get("WRank") or 200.0)
        r_l = float(row.get("LRank") or 200.0)

        diff_rank = (r_l - r_w) / max(r_w, r_l, 1.0)
        diff_form = (form_w - form_l) / 100.0
        diff_surf = (surf_w - surf_l) / 100.0
        diff_elo = (elo_w - elo_l) / 400.0

        sign = 1.0 if int(idx) % 2 == 0 else -1.0
        buckets[bucket][0].append([sign * diff_rank, sign * diff_form, sign * diff_surf, sign * diff_elo])
        buckets[bucket][1].append(1.0 if sign > 0 else 0.0)

    return buckets


def calibrate_from_dataframe(
    df: pd.DataFrame, output_path: str = DEFAULT_WEIGHTS_PATH
) -> Dict[str, Any]:
    """Calibre les poids par surface à partir d'un DataFrame de matchs historiques."""
    stats_engine = PointInTimeStats(df)
    buckets = _extract_surface_samples(df, stats_engine)
    calibrated: Dict[str, Any] = {}

    for surf, (x_list, y_list) in buckets.items():
        if len(x_list) < 20:
            calibrated[surf] = dict(DEFAULT_SURFACE_WEIGHTS[surf], samples=len(x_list))
            continue

        x_arr = np.asarray(x_list, dtype=float)
        y_arr = np.asarray(y_list, dtype=float)
        opt_w, b_before, b_after = _fit_logistic_weights(x_arr, y_arr)

        calibrated[surf] = {
            "rank": round(float(opt_w[0]) * 6.0, 2),
            "form": round(float(opt_w[1]) * 25.0, 2),
            "surface": round(float(opt_w[2]) * 30.0, 2),
            "elo": round(float(opt_w[3]) * 0.20, 4),
            "trj": 0.90,
            "samples": len(x_list),
            "brier_before": round(b_before, 4),
            "brier_after": round(b_after, 4),
        }

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f_out:
        json.dump(calibrated, f_out, indent=2)
    return calibrated


def calibrate_from_archives(
    data_dir: str = "backtest/data", output_path: str = DEFAULT_WEIGHTS_PATH
) -> Dict[str, Any]:
    """Charge toutes les archives 2022-2026 disponibles et lance la calibration."""
    frames = []
    for gender in ("atp", "wta"):
        for year in (2022, 2023, 2024, 2025, 2026):
            path = os.path.join(data_dir, f"{gender}_{year}.xlsx")
            if os.path.exists(path):
                frames.append(pd.read_excel(path))
    if not frames:
        return calibrate_from_dataframe(pd.DataFrame(), output_path=output_path)
    combined = pd.concat(frames, ignore_index=True)
    return calibrate_from_dataframe(combined, output_path=output_path)


if __name__ == "__main__":
    result = calibrate_from_archives()
    print(json.dumps(result, indent=2))