"""Tests unitaires pour la calibration empirique des poids par surface."""

import json
import pandas as pd
from backtest.calibrate_weights import calibrate_from_dataframe


def test_calibrate_weights_improves_or_preserves_brier_score(tmp_path):
    """Vérifie que l'optimiseur L-BFGS-B calibre les poids sur terre battue."""
    rows = []
    for idx in range(60):
        day = f"2024-05-{(idx % 28) + 1:02d}"
        # Favori clair (Player Strong) gagne majoritairement sur Clay
        if idx % 5 != 0:
            rows.append({
                "Date": day,
                "Surface": "Clay",
                "Comment": "Completed",
                "Winner": "Player Strong",
                "Loser": "Player Weak",
                "WRank": 5,
                "LRank": 95,
            })
        else:
            rows.append({
                "Date": day,
                "Surface": "Clay",
                "Comment": "Completed",
                "Winner": "Player Weak",
                "Loser": "Player Strong",
                "WRank": 95,
                "LRank": 5,
            })

    df = pd.DataFrame(rows)
    out_json = str(tmp_path / "calibrated_weights.json")
    calibrated = calibrate_from_dataframe(df, output_path=out_json)

    assert "clay" in calibrated
    assert calibrated["clay"]["brier_after"] <= calibrated["clay"]["brier_before"]
    with open(out_json, "r", encoding="utf-8") as f_in:
        saved = json.load(f_in)
    assert saved["clay"]["samples"] >= 20