"""Calibration empirique directe du modèle compare_players par surface (validation temporelle)."""

import json
import os
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from analysis.compare_players import (
    _DEFAULT_WEIGHTS,
    _MAX_PROB,
    _MIN_PROB,
    extract_scoring_components,
)
from backtest.point_in_time_stats import PointInTimeStats
from core.models import MatchAnalysisData, PlayerStats
from utils.helpers import normalize_surface, safe_int

DEFAULT_WEIGHTS_PATH = "config/calibrated_weights.json"
DEFAULT_SURFACE_WEIGHTS = _DEFAULT_WEIGHTS

_TRAIN_RATIO = 0.80
_ANCHOR_REG = 1e-5
_WEIGHT_BOUNDS = [(0.5, 15.0), (5.0, 50.0), (5.0, 50.0), (0.0, 0.50)]


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


def _predict_compare_players_probs(
    comp_matrix: np.ndarray, weights_vec: np.ndarray
) -> np.ndarray:
    """Évalue vectoriellement la probabilité exacte produite par compare_players().

    Colonnes de comp_matrix :
    [fixed_a, fixed_b, rank_a, rank_b, form_a, form_b, surf_a, surf_b, elo_a, elo_b]
    """
    w_rank, w_form, w_surf, w_elo = weights_vec
    score_a = (
        comp_matrix[:, 0]
        + w_rank * comp_matrix[:, 2]
        + w_form * comp_matrix[:, 4]
        + w_surf * comp_matrix[:, 6]
        + w_elo * comp_matrix[:, 8]
    )
    score_b = (
        comp_matrix[:, 1]
        + w_rank * comp_matrix[:, 3]
        + w_form * comp_matrix[:, 5]
        + w_surf * comp_matrix[:, 7]
        + w_elo * comp_matrix[:, 9]
    )
    safe_a = np.maximum(0.0, score_a)
    safe_b = np.maximum(0.0, score_b)
    total = safe_a + safe_b
    probs = np.where(total > 0.0, safe_a / np.where(total > 0.0, total, 1.0), 0.5)
    return np.clip(probs, _MIN_PROB, _MAX_PROB)


def _fit_direct_model_weights(
    c_train: np.ndarray,
    y_train: np.ndarray,
    c_val: np.ndarray,
    y_val: np.ndarray,
    default_cfg: Dict[str, float],
) -> Tuple[np.ndarray, float, float, float, float]:
    """Optimise [rank, form, surface, elo] directement sur compare_players()."""
    init_w = np.array(
        [default_cfg["rank"], default_cfg["form"], default_cfg["surface"], default_cfg["elo"]],
        dtype=float,
    )
    base_val_probs = _predict_compare_players_probs(c_val, init_w)
    brier_before = brier_score(y_val, base_val_probs)
    ll_before = log_loss(y_val, base_val_probs)

    scales = np.array([5.0, 20.0, 30.0, 0.15], dtype=float)

    def _objective(weights: np.ndarray) -> float:
        probs = _predict_compare_players_probs(c_train, weights)
        reg = _ANCHOR_REG * float(np.sum(((weights - init_w) / scales) ** 2))
        return brier_score(y_train, probs) + reg

    res = minimize(
        _objective,
        init_w,
        method="Powell",
        bounds=_WEIGHT_BOUNDS,
        options={"maxiter": 600, "ftol": 1e-6},
    )
    opt_w = np.clip(res.x, [b[0] for b in _WEIGHT_BOUNDS], [b[1] for b in _WEIGHT_BOUNDS])
    opt_val_probs = _predict_compare_players_probs(c_val, opt_w)
    brier_after = brier_score(y_val, opt_val_probs)
    ll_after = log_loss(y_val, opt_val_probs)
    return opt_w, brier_before, brier_after, ll_before, ll_after


def _build_player_stats(
    name: str, rank: int, elo: float, profile: Dict[str, float]
) -> PlayerStats:
    return PlayerStats(
        name=name,
        ranking=rank,
        elo=elo,
        win_pct_last_10=float(profile["win_pct_last_10"]),
        win_pct_last_50=float(profile["win_pct_last_50"]),
        win_pct_1y=float(profile["win_pct_1y"]),
        win_pct_career=float(profile["win_pct_career"]),
        win_pct_1y_surface=float(profile["win_pct_1y_surface"]),
        win_pct_career_surface=float(profile["win_pct_career_surface"]),
        matches_last_month=int(profile["matches_last_month"]),
        data_sources={"point_in_time"},
    )


def _extract_surface_samples(
    df: pd.DataFrame, stats_engine: PointInTimeStats
) -> Dict[str, Tuple[List[Tuple[float, ...]], List[float], List[str]]]:
    """Construit les matrices exactes compare_players triées chronologiquement par surface."""
    buckets: Dict[str, Tuple[List[Tuple[float, ...]], List[float], List[str]]] = {
        "hard": ([], [], []),
        "clay": ([], [], []),
        "grass": ([], [], []),
    }
    if df.empty:
        return buckets

    completed = df[df["Comment"] == "Completed"].copy() if "Comment" in df.columns else df.copy()
    if completed.empty:
        return buckets

    completed["Date"] = pd.to_datetime(completed["Date"])
    completed = completed.sort_values("Date").reset_index(drop=True)

    for idx, row in completed.iterrows():
        p_w, p_l = str(row["Winner"]), str(row["Loser"])
        m_date = row["Date"]
        surf = str(row.get("Surface", "Hard"))
        bucket = normalize_surface(surf)

        prof_w = stats_engine.get_player_profile_before(p_w, m_date, surf)
        prof_l = stats_engine.get_player_profile_before(p_l, m_date, surf)
        if int(prof_w["matches_1y"]) < 3 or int(prof_l["matches_1y"]) < 3:
            continue

        elo_w = stats_engine.get_player_elo_before(p_w, m_date, surf)
        elo_l = stats_engine.get_player_elo_before(p_l, m_date, surf)
        r_w = safe_int(row.get("WRank"), default=200) or 200
        r_l = safe_int(row.get("LRank"), default=200) or 200

        ps_w = _build_player_stats(p_w, r_w, elo_w, prof_w)
        ps_l = _build_player_stats(p_l, r_l, elo_l, prof_l)

        # Symétrie positionnelle (alterne vainqueur en J1 / J2)
        if int(idx) % 2 == 0:
            h2h = stats_engine.get_h2h_before(p_w, p_l, m_date, surf)
            match_obj = MatchAnalysisData(
                match_url="", surface=surf, player_a=ps_w, player_b=ps_l, h2h=h2h
            )
            label = 1.0
        else:
            h2h = stats_engine.get_h2h_before(p_l, p_w, m_date, surf)
            match_obj = MatchAnalysisData(
                match_url="", surface=surf, player_a=ps_l, player_b=ps_w, h2h=h2h
            )
            label = 0.0

        buckets[bucket][0].append(extract_scoring_components(match_obj))
        buckets[bucket][1].append(label)
        buckets[bucket][2].append(m_date.strftime("%Y-%m-%d"))

    return buckets


def calibrate_from_dataframe(
    df: pd.DataFrame,
    output_path: str = DEFAULT_WEIGHTS_PATH,
    max_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Calibre directement compare_players() avec validation temporelle stricte (80/20)."""
    working_df = df.copy()
    if max_date and not working_df.empty and "Date" in working_df.columns:
        working_df["Date"] = pd.to_datetime(working_df["Date"])
        working_df = working_df[working_df["Date"] < pd.to_datetime(max_date)]

    stats_engine = PointInTimeStats(working_df)
    buckets = _extract_surface_samples(working_df, stats_engine)
    calibrated: Dict[str, Any] = {}

    for surf, (c_list, y_list, d_list) in buckets.items():
        default_cfg = DEFAULT_SURFACE_WEIGHTS[surf]
        if len(c_list) < 20:
            calibrated[surf] = {
                **default_cfg,
                "samples": len(c_list),
                "accepted": False,
                "trained_until": d_list[-1] if d_list else "",
            }
            continue

        c_arr = np.asarray(c_list, dtype=float)
        y_arr = np.asarray(y_list, dtype=float)
        split_idx = max(10, min(len(c_arr) - 5, int(len(c_arr) * _TRAIN_RATIO)))

        opt_w, b_before, b_after, ll_before, ll_after = _fit_direct_model_weights(
            c_arr[:split_idx], y_arr[:split_idx], c_arr[split_idx:], y_arr[split_idx:], default_cfg
        )

        accepted = b_after < b_before
        chosen_weights = (
            {
                "rank": round(float(opt_w[0]), 2),
                "form": round(float(opt_w[1]), 2),
                "surface": round(float(opt_w[2]), 2),
                "elo": round(float(opt_w[3]), 4),
                "trj": 0.90,
            }
            if accepted
            else dict(default_cfg)
        )
        calibrated[surf] = {
            **chosen_weights,
            "samples": len(c_list),
            "train_samples": split_idx,
            "val_samples": len(c_list) - split_idx,
            "trained_until": d_list[-1],
            "train_end": d_list[split_idx - 1],
            "val_start": d_list[split_idx],
            "val_end": d_list[-1],
            "accepted": accepted,
            "brier_before": round(b_before, 6),
            "brier_after": round(b_after if accepted else b_before, 6),
            "candidate_brier_after": round(b_after, 6),
            "logloss_before": round(ll_before, 6),
            "logloss_after": round(ll_after if accepted else ll_before, 6),
        }

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f_out:
        json.dump(calibrated, f_out, indent=2)
    return calibrated


def calibrate_from_archives(
    data_dir: str = "backtest/data",
    output_path: str = DEFAULT_WEIGHTS_PATH,
    max_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Charge toutes les archives 2022-2026 disponibles et lance la calibration directe."""
    frames = []
    for gender in ("atp", "wta"):
        for year in (2022, 2023, 2024, 2025, 2026):
            path = os.path.join(data_dir, f"{gender}_{year}.xlsx")
            if os.path.exists(path):
                frames.append(pd.read_excel(path))
    if not frames:
        return calibrate_from_dataframe(pd.DataFrame(), output_path=output_path)
    combined = pd.concat(frames, ignore_index=True)
    return calibrate_from_dataframe(combined, output_path=output_path, max_date=max_date)


if __name__ == "__main__":
    result = calibrate_from_archives()
    print(json.dumps(result, indent=2))
