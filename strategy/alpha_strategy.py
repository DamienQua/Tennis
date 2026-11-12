"""
Alpha 5+ All-Court Betting Strategy Module.

Calculates the Alpha 5+ signal based on model odds, market odds, and Elo ratings:
- Expected Value (EV) > +3.0% (P_model * Bookmaker Odds > 1.03)
- Elo Gap >= 150 points in favor of the candidate
- Bookmaker Odds in [1.40, 2.50]
- Valid on all surfaces (Clay, Hard, Grass)
"""

from typing import Dict, Any, Tuple
from utils.helpers import get_arg

def _safe_float(val: Any) -> float:
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError, AttributeError):
        return 0.0

def _calculate_probabilities(model_1: float, model_2: float) -> Tuple[float, float]:
    if model_1 <= 1.01 or model_2 <= 1.01:
        return 0.0, 0.0
    p1_raw = 0.90 / model_1
    p2_raw = 0.90 / model_2
    tot = p1_raw + p2_raw
    if tot <= 0:
        return 0.0, 0.0
    return p1_raw / tot, p2_raw / tot

def _calc_raw_ev(prob: float, book_odds: float) -> float:
    if prob > 0 and book_odds > 0:
        return prob * book_odds - 1.0
    return 0.0

def _check_candidate(prob: float, book_odds: float, elo_diff: float) -> Tuple[bool, float]:
    ev = _calc_raw_ev(prob, book_odds)
    in_range = (1.40 <= book_odds <= 2.50)
    meets_criteria = in_range and (ev > 0.03) and (elo_diff >= 150.0)
    return meets_criteria, ev

def _format_pct(val: float, is_valid: bool) -> str:
    if not is_valid:
        return "-"
    return f"{val * 100:+.1f}%"

def _format_diff(val: float, is_valid: bool) -> str:
    if not is_valid:
        return "-"
    return f"{val:+0.0f}"

def _build_bet_result(
    player: str, index: int, odds: Tuple[float, float, float], metrics: Tuple[float, float]
) -> Dict[str, Any]:
    book, model, prob = odds
    ev, elo_diff = metrics
    return {
        "bet_recommended": True,
        "selected_player": player,
        "player_index": index,
        "book_odds": book,
        "model_odds": model,
        "model_prob": prob,
        "ev": ev,
        "ev_percent": round(ev * 100, 2),
        "elo_diff": elo_diff,
        "signal_j1": "PARI CONSEILLÉ" if index == 1 else "-",
        "signal_j2": "PARI CONSEILLÉ" if index == 2 else "-"
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
        "signal_j1": reason,
        "signal_j2": reason
    }

def _assemble_final_dict(
    base: Dict[str, Any],
    data_valid: bool,
    ev_pair: Tuple[float, float],
    diff_pair: Tuple[float, float]
) -> Dict[str, Any]:
    ev_1, ev_2 = ev_pair
    diff_1, diff_2 = diff_pair
    base["ev_j1_str"] = _format_pct(ev_1, data_valid)
    base["ev_j2_str"] = _format_pct(ev_2, data_valid)
    base["elo_diff_j1_str"] = _format_diff(diff_1, data_valid)
    base["elo_diff_j2_str"] = _format_diff(diff_2, data_valid)
    base["summary"] = format_alpha_summary(base)
    return base

def format_alpha_summary(res: Dict[str, Any]) -> str:
    if res.get("bet_recommended"):
        p = res["selected_player"]
        b = res["book_odds"]
        ev = res["ev_percent"]
        diff = res["elo_diff"]
        return (
            f"🎯 SIGNAL ALPHA 5+: Pari conseillé sur {p} @ {b:.2f} "
            f"(EV: {ev:+.1f}%, ΔELO: {diff:+.0f})"
        )
    return (
        f"⚪ Stratégie Alpha 5+: Aucun signal "
        f"(EV J1: {res.get('ev_j1_str', '-')}, EV J2: {res.get('ev_j2_str', '-')})"
    )

def _is_valid_input(odds: Tuple[float, ...], elos: Tuple[float, ...]) -> bool:
    return (min(odds) > 1.01) and (min(elos) > 0)

def evaluate_alpha_strategy(
    *args,
    player_1: str = "Joueur 1",
    player_2: str = "Joueur 2",
    **kwargs
) -> Dict[str, Any]:
    model_1 = get_arg(args, 0, kwargs.get("model_1", 0.0))
    model_2 = get_arg(args, 1, kwargs.get("model_2", 0.0))
    book_1 = get_arg(args, 2, kwargs.get("book_1", 0.0))
    book_2 = get_arg(args, 3, kwargs.get("book_2", 0.0))
    elo_1 = get_arg(args, 4, kwargs.get("elo_1", 0.0))
    elo_2 = get_arg(args, 5, kwargs.get("elo_2", 0.0))
    player_1 = get_arg(args, 6, kwargs.get("player_1", player_1))
    player_2 = get_arg(args, 7, kwargs.get("player_2", player_2))

    m1, m2 = _safe_float(model_1), _safe_float(model_2)
    b1, b2 = _safe_float(book_1), _safe_float(book_2)
    e1, e2 = _safe_float(elo_1), _safe_float(elo_2)

    data_valid = _is_valid_input((m1, m2, b1, b2), (e1, e2))
    p1, p2 = _calculate_probabilities(m1, m2)
    diff_1, diff_2 = e1 - e2, e2 - e1

    ok_1, ev_1 = _check_candidate(p1, b1, diff_1)
    ok_2, ev_2 = _check_candidate(p2, b2, diff_2)

    if ok_1:
        base = _build_bet_result(player_1, 1, (b1, m1, p1), (ev_1, diff_1))
    elif ok_2:
        base = _build_bet_result(player_2, 2, (b2, m2, p2), (ev_2, diff_2))
    else:
        base = _build_no_bet_result(data_valid)

    return _assemble_final_dict(base, data_valid, (ev_1, ev_2), (diff_1, diff_2))
