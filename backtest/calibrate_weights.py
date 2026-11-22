"""Calibration empirique des poids du modèle par surface avec validation hors échantillon."""

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

_INIT_LOGISTIC_WEIGHTS = np.array([0.8, 0.8, 1.2, 1.0], dtype=float)
_L2_REG = 1e-4
_TRAIN_RATIO = 0.80


def _surface_bucket(surface: str) -> str:
    s_low = surface.strip().lower()
    if "clay" in s_low:
        return "clay"
    if "grass" in s_low:
        return "grass"
    return "hard"


def _safe_rank(val: Any, default: float = 200.0) -> float:
    if pd.isna(val):
        return default
    try:
        parsed = float(val)
        return parsed if parsed > 0 else default
    except (ValueError, TypeError):
        return default


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
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    l2_reg: float = _L2_REG,
) -> Tuple[np.ndarray, float, float, float, float]:
    """Optimise [rank, form, surface, elo] sur Train et évalue Log-Loss / Brier sur Validation."""
    init_val_probs = _sigmoid(x_val @ _INIT_LOGISTIC_WEIGHTS)
    brier_before = brier_score(y_val, init_val_probs)
    ll_before = log_loss(y_val, init_val_probs)

    def _objective(weights: np.ndarray) -> float:
        probs = _sigmoid(x_train @ weights)
        return log_loss(y_train, probs) + l2_reg * float(np.sum(weights ** 2))

    res = minimize(
        _objective,
        _INIT_LOGISTIC_WEIGHTS,
        method="L-BFGS-B",
        bounds=[(0.0, 10.0), (0.0, 10.0), (0.0, 10.0), (0.0, 10.0)],
    )
    opt_w = res.x
    opt_val_probs = _sigmoid(x_val @ opt_w)
    brier_after = brier_score(y_val, opt_val_probs)
    ll_after = log_loss(y_val, opt_val_probs)
    return opt_w, brier_before, brier_after, ll_before, ll_after


def _map_to_model_weights(
    opt_w: np.ndarray, default_cfg: Dict[str, float]
) -> Dict[str, float]:
    """Projette les poids logistiques sur l'échelle de compare_players.py sans écraser form/surface."""
    w_rank, w_form, w_surf, w_elo = [float(v) for v in opt_w]
    form_surf_sum = w_form + w_surf
    if form_surf_sum > 1e-6:
        form_w = round(min(max(50.0 * (w_form / form_surf_sum), 10.0), 40.0), 2)
        surf_w = round(50.0 - form_w, 2)
    else:
        form_w = default_cfg["form"]
        surf_w = default_cfg["surface"]

    rank_w = round(min(max(w_rank * 4.0, 1.0), 10.0), 2)
    elo_w = round(min(max(w_elo * 0.15, 0.05), 0.35), 4)
    return {
        "rank": rank_w,
        "form": form_w,
        "surface": surf_w,
        "elo": elo_w,
        "trj": 0.90,
    }


def _extract_surface_samples(
    df: pd.DataFrame, stats_engine: PointInTimeStats
) -> Dict[str, Tuple[List[List[float]], List[float]]]:
    """Construit les vecteurs symétriques (X, y) triés chronologiquement sans look-ahead bias."""
    buckets: Dict[str, Tuple[List[List[float]], List[float]]] = {
        "hard": ([], []),
        "clay": ([], []),
        "grass": ([], []),
    }
    if df.empty:
        return buckets

    completed = df[df["Comment"] == "Completed"].copy() if "Comment" in df.columns else df.copy()
    if completed.empty:
        return buckets

    completed["Date"] = pd.to_datetime(completed["Date"])
    completed.sort_values("Date", inplace=True)
    completed.reset_index(drop=True, inplace=True)

    for idx, row in completed.iterrows():
        p_w, p_l = str(row["Winner"]), str(row["Loser"])
        m_date = row["Date"]
        surf = str(row.get("Surface", "Hard"))
        bucket = _surface_bucket(surf)

        form_w, surf_w, cnt_w = stats_engine.get_player_stats_before(p_w, m_date, surf)
        form_l, surf_l, cnt_l = stats_engine.get_player_stats_before(p_l, m_date, surf)
        if cnt_w < 3 or cnt_l < 3:
            continue

        elo_w = stats_engine.get_player_elo_before(p_w, m_date, surf)
        elo_l = stats_engine.get_player_elo_before(p_l, m_date, surf)
        r_w = _safe_rank(row.get("WRank"))
        r_l = _safe_rank(row.get("LRank"))

        diff_rank = (r_l - r_w) / max(r_w, r_l, 1.0)
        diff_form = (form_w - form_l) / 100.0
        diff_surf = (surf_w - surf_l) / 100.0
        diff_elo = (elo_w - elo_l) / 400.0

        sign = 1.0 if int(idx) % 2 == 0 else -1.0
        buckets[bucket][0].append(
            [sign * diff_rank, sign * diff_form, sign * diff_surf, sign * diff_elo]
        )
        buckets[bucket][1].append(1.0 if sign > 0 else 0.0)

    return buckets


def calibrate_from_dataframe(
    df: pd.DataFrame, output_path: str = DEFAULT_WEIGHTS_PATH
) -> Dict[str, Any]:
    """Calibre les poids par surface avec validation chronologique Train/Test (80/20)."""
    stats_engine = PointInTimeStats(df)
    buckets = _extract_surface_samples(df, stats_engine)
    calibrated: Dict[str, Any] = {}

    for surf, (x_list, y_list) in buckets.items():
        default_cfg = DEFAULT_SURFACE_WEIGHTS[surf]
        if len(x_list) < 20:
            calibrated[surf] = {**default_cfg, "samples": len(x_list), "accepted": False}
            continue

        x_arr = np.asarray(x_list, dtype=float)
        y_arr = np.asarray(y_list, dtype=float)
        split_idx = max(10, min(len(x_arr) - 5, int(len(x_arr) * _TRAIN_RATIO)))

        opt_w, b_before, b_after, ll_before, ll_after = _fit_logistic_weights(
            x_arr[:split_idx], y_arr[:split_idx], x_arr[split_idx:], y_arr[split_idx:]
        )

        accepted = b_after <= b_before
        chosen_weights = (
            _map_to_model_weights(opt_w, default_cfg) if accepted else dict(default_cfg)
        )
        calibrated[surf] = {
            **chosen_weights,
            "samples": len(x_list),
            "train_samples": split_idx,
            "val_samples": len(x_list) - split_idx,
            "accepted": accepted,
            "brier_before": round(b_before, 4),
            "brier_after": round(b_after if accepted else b_before, 4),
            "candidate_brier_after": round(b_after, 4),
            "logloss_before": round(ll_before, 4),
            "logloss_after": round(ll_after if accepted else ll_before, 4),
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
