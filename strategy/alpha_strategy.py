"""Stratégie de détection Value Betting Alpha 5+ All-Court avec dimensionnement Kelly."""

from typing import Any, Dict, Tuple
from core.models import MatchAnalysisData

MIN_BOOK_ODDS = 1.40
MAX_BOOK_ODDS = 2.50
MIN_EV_THRESHOLD = 0.03
MIN_ELO_GAP = 150.0
MODEL_MARGIN = 0.90

KELLY_FRACTION = 0.25  # Quart de Kelly pour limiter la variance
MAX_STAKE_PCT = 3.0    # Plafond à 3% de la bankroll par pari


def _calculate_probabilities(model_1: float, model_2: float) -> Tuple[float, float]:
    if model_1 <= 1.01 or model_2 <= 1.01:
        return 0.0, 0.0
    p1_raw = MODEL_MARGIN / model_1
    p2_raw = MODEL_MARGIN / model_2
    tot = p1_raw + p2_raw
    if tot <= 0:
        return 0.0, 0.0
    return p1_raw / tot, p2_raw / tot


def _calc_raw_ev(prob: float, book_odds: float) -> float:
    return (prob * book_odds - 1.0) if (prob > 0 and book_odds > 0) else 0.0


def calculate_kelly_stake(prob: float, book_odds: float) -> float:
    """Calcule la mise conseillée en % de bankroll via Kelly fractionné."""
    if book_odds <= 1.0 or prob <= 0.0:
        return 0.0
    net_odds = book_odds - 1.0
    full_kelly = (prob * net_odds - (1.0 - prob)) / net_odds
    if full_kelly <= 0.0:
        return 0.0
    fractional_pct = full_kelly * KELLY_FRACTION * 100.0
    return round(min(fractional_pct, MAX_STAKE_PCT), 2)


def _check_candidate(prob: float, book_odds: float, elo_diff: float) -> Tuple[bool, float]:
    raw_ev = _calc_raw_ev(prob, book_odds)
    in_range = MIN_BOOK_ODDS <= book_odds <= MAX_BOOK_ODDS
    meets_criteria = in_range and (raw_ev > MIN_EV_THRESHOLD) and (elo_diff >= MIN_ELO_GAP)
    return meets_criteria, raw_ev


def _build_bet_result(
    player: str, index: int, odds: Tuple[float, float, float], metrics: Tuple[float, float]
) -> Dict[str, Any]:
    book, model, prob = odds
    exp_val, elo_diff = metrics
    kelly_pct = calculate_kelly_stake(prob, book)
    return {
        "bet_recommended": True,
        "selected_player": player,
        "player_index": index,
        "book_odds": book,
        "model_odds": model,
        "model_prob": prob,
        "ev": exp_val,
        "ev_percent": round(exp_val * 100, 2),
        "elo_diff": elo_diff,
        "kelly_stake_pct": kelly_pct,
        "signal_j1": f"PARI CONSEILLÉ ({kelly_pct:.2f}%)" if index == 1 else "-",
        "signal_j2": f"PARI CONSEILLÉ ({kelly_pct:.2f}%)" if index == 2 else "-",
    }


def _build_no_bet_result(data_valid: bool) -> Dict[str, Any]:
    reason = "-" if data_valid else "Données incomplètes"
    return {
        "bet_recommended": False,
        "selected_player": "",
        "player_index": 0,
        "book_odds": 0.0,
        "model_odds": 0.0,
        "model_prob": 0.0,
        "ev": 0.0,
        "ev_percent": 0.0,
        "elo_diff": 0.0,
        "kelly_stake_pct": 0.0,
        "signal_j1": reason,
        "signal_j2": reason,
    }


def format_alpha_summary(res: Dict[str, Any]) -> str:
    """Formate le résumé console du signal Alpha 5+."""
    if res.get("bet_recommended"):
        return (
            f"SIGNAL ALPHA 5+: Pari conseillé sur {res['selected_player']} "
            f"@ {res['book_odds']:.2f} (EV: {res['ev_percent']:+.1f}%, "
            f"ΔELO: {res['elo_diff']:+.0f}, Mise Kelly: {res['kelly_stake_pct']:.2f}%)"
        )
    return (
        f"Stratégie Alpha 5+: Aucun signal "
        f"(EV J1: {res.get('ev_j1_str', '-')}, EV J2: {res.get('ev_j2_str', '-')})"
    )


def evaluate_alpha_strategy(match: MatchAnalysisData) -> Dict[str, Any]:
    """Évalue la stratégie Alpha 5+ sur un match typé."""
    pa, pb = match.player_a, match.player_b
    data_valid = (
        min(pa.model_odds, pb.model_odds, pa.book_odds, pb.book_odds) > 1.01
        and min(pa.elo, pb.elo) > 0
    )
    probs = _calculate_probabilities(pa.model_odds, pb.model_odds)
    diffs = (pa.elo - pb.elo, pb.elo - pa.elo)
    cand_1 = _check_candidate(probs[0], pa.book_odds, diffs[0])
    cand_2 = _check_candidate(probs[1], pb.book_odds, diffs[1])

    if cand_1[0]:
        base = _build_bet_result(
            pa.name, 1, (pa.book_odds, pa.model_odds, probs[0]), (cand_1[1], diffs[0])
        )
    elif cand_2[0]:
        base = _build_bet_result(
            pb.name, 2, (pb.book_odds, pb.model_odds, probs[1]), (cand_2[1], diffs[1])
        )
    else:
        base = _build_no_bet_result(data_valid)

    base["ev_j1_str"] = f"{cand_1[1] * 100:+.1f}%" if data_valid else "-"
    base["ev_j2_str"] = f"{cand_2[1] * 100:+.1f}%" if data_valid else "-"
    base["elo_diff_j1_str"] = f"{diffs[0]:+0.0f}" if data_valid else "-"
    base["elo_diff_j2_str"] = f"{diffs[1]:+0.0f}" if data_valid else "-"
    base["summary"] = format_alpha_summary(base)
    return base