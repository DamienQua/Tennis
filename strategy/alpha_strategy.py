"""Stratégie de détection Value Betting Alpha 5+ All-Court."""

from typing import Any, Dict, Tuple
from core.models import MatchAnalysisData

MIN_BOOK_ODDS = 1.40
MAX_BOOK_ODDS = 2.50
MIN_EV_THRESHOLD = 0.03
MIN_ELO_GAP = 150.0
MODEL_MARGIN = 0.90


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


def _check_candidate(prob: float, book_odds: float, elo_diff: float) -> Tuple[bool, float]:
    raw_ev = _calc_raw_ev(prob, book_odds)
    in_range = MIN_BOOK_ODDS <= book_odds <= MAX_BOOK_ODDS
    meets_criteria = in_range and (raw_ev > MIN_EV_THRESHOLD) and (elo_diff >= MIN_ELO_GAP)
    return meets_criteria, raw_ev


def _format_pct(val: float, is_valid: bool) -> str:
    return f"{val * 100:+.1f}%" if is_valid else "-"


def _format_diff(val: float, is_valid: bool) -> str:
    return f"{val:+0.0f}" if is_valid else "-"


def _build_bet_result(
    player: str, index: int, odds: Tuple[float, float, float], metrics: Tuple[float, float]
) -> Dict[str, Any]:
    book, model, prob = odds
    exp_val, elo_diff = metrics
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
        "signal_j1": "PARI CONSEILLÉ" if index == 1 else "-",
        "signal_j2": "PARI CONSEILLÉ" if index == 2 else "-",
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
        "signal_j2": reason,
    }


def _assemble_final_dict(
    base: Dict[str, Any],
    data_valid: bool,
    ev_pair: Tuple[float, float],
    diff_pair: Tuple[float, float],
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
    """Formate le résumé console du signal Alpha 5+."""
    if res.get("bet_recommended"):
        return (
            f"SIGNAL ALPHA 5+: Pari conseillé sur {res['selected_player']} "
            f"@ {res['book_odds']:.2f} (EV: {res['ev_percent']:+.1f}%, "
            f"ΔELO: {res['elo_diff']:+.0f})"
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

    return _assemble_final_dict(base, data_valid, (cand_1[1], cand_2[1]), diffs)