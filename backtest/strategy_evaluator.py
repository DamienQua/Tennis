"""
Strategy evaluator for tennis betting backtesting.

Simulates bets placed based on model predictions versus historical market odds,
and calculates performance metrics (P&L, ROI, Win Rate, Drawdown).
"""

from typing import List, Dict, Any
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from strategy.alpha_strategy import evaluate_alpha_strategy

class BetRecord:
    def __init__(
        self,
        match_name: str,
        tournament: str,
        bet_on: str,
        model_odds: float,
        market_odds: float,
        won: bool,
        stake: float = 1.0
    ):
        self.match_name = match_name
        self.tournament = tournament
        self.bet_on = bet_on
        self.model_odds = model_odds
        self.market_odds = market_odds
        self.won = won
        self.stake = stake
        self.pnl = round(stake * (market_odds - 1), 2) if won else -round(stake, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "match": self.match_name,
            "tournament": self.tournament,
            "bet_on": self.bet_on,
            "model_odds": self.model_odds,
            "market_odds": self.market_odds,
            "won": self.won,
            "stake": self.stake,
            "pnl": self.pnl
        }

def _to_float(val: Any) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

class StrategyEvaluator:
    """Evaluates betting performance across a collection of match predictions."""

    def __init__(self, value_edge_threshold: float = 0.05, stake_size: float = 1.0):
        self.value_edge_threshold = value_edge_threshold
        self.stake_size = stake_size
        self.bets: List[BetRecord] = []

    @staticmethod
    def _is_ok_j1(
        excel_j1: float,
        excel_j2: float,
        book_j1: float,
        book_j2: float,
        elo_j1: float,
        elo_j2: float,
        surface_j1: float,
        surface_j2: float
    ) -> bool:
        ej1, ej2 = _to_float(excel_j1), _to_float(excel_j2)
        bj1, bj2 = _to_float(book_j1), _to_float(book_j2)
        el1, el2 = _to_float(elo_j1), _to_float(elo_j2)
        s1, s2 = _to_float(surface_j1), _to_float(surface_j2)

        return (
            ej1 < ej2 and
            bj1 < bj2 and
            el1 > el2 and
            s1 > s2 and
            bj1 > ej1
        )

    @staticmethod
    def _is_ok_j2(
        excel_j1: float,
        excel_j2: float,
        book_j1: float,
        book_j2: float,
        elo_j1: float,
        elo_j2: float,
        surface_j1: float,
        surface_j2: float
    ) -> bool:
        ej1, ej2 = _to_float(excel_j1), _to_float(excel_j2)
        bj1, bj2 = _to_float(book_j1), _to_float(book_j2)
        el1, el2 = _to_float(elo_j1), _to_float(elo_j2)
        s1, s2 = _to_float(surface_j1), _to_float(surface_j2)

        return (
            ej1 > ej2 and
            bj1 > bj2 and
            el1 < el2 and
            s1 < s2 and
            bj2 > ej2
        )

    @classmethod
    def evaluate_confluence(
        cls,
        excel_j1: float,
        excel_j2: float,
        book_j1: float,
        book_j2: float,
        elo_j1: float,
        elo_j2: float,
        surface_j1: float,
        surface_j2: float
    ) -> str:
        if cls._is_ok_j1(
            excel_j1, excel_j2, book_j1, book_j2, elo_j1, elo_j2, surface_j1, surface_j2
        ):
            return "OK J1"
        if cls._is_ok_j2(
            excel_j1, excel_j2, book_j1, book_j2, elo_j1, elo_j2, surface_j1, surface_j2
        ):
            return "OK J2"
        return "PAS OK"

    @classmethod
    def evaluate_alpha_5_plus(
        cls,
        model_1: Any,
        model_2: Any,
        book_1: Any,
        book_2: Any,
        elo_1: Any,
        elo_2: Any,
        player_1: str = "J1",
        player_2: str = "J2"
    ) -> Dict[str, Any]:
        return evaluate_alpha_strategy(
            model_1, model_2, book_1, book_2, elo_1, elo_2, player_1, player_2
        )

    @classmethod
    def evaluate_optimized_confluence(
        cls,
        excel_j1: float,
        excel_j2: float,
        book_j1: float,
        book_j2: float,
        elo_j1: float,
        elo_j2: float,
        surface_j1: float,
        surface_j2: float,
        surface: str = "Clay"
    ) -> str:
        s_clean = surface.lower()
        if "grass" in s_clean:
            return "PAS OK"

        raw = cls.evaluate_confluence(
            excel_j1, excel_j2, book_j1, book_j2, elo_j1, elo_j2, surface_j1, surface_j2
        )
        if raw == "PAS OK":
            return "PAS OK"

        elo_diff = abs(_to_float(elo_j1) - _to_float(elo_j2))
        bet_odds = _to_float(book_j1) if raw == "OK J1" else _to_float(book_j2)

        if "clay" in s_clean:
            return raw if elo_diff >= 50.0 else "PAS OK"
        if "hard" in s_clean:
            return raw if (elo_diff >= 120.0 and bet_odds <= 1.50) else "PAS OK"

        return "PAS OK"

    def evaluate_match_confluence(
        self,
        player_a: str,
        player_b: str,
        tournament: str,
        excel_j1: float,
        excel_j2: float,
        book_j1: float,
        book_j2: float,
        elo_j1: float,
        elo_j2: float,
        surface_j1: float,
        surface_j2: float,
        winner: str
    ) -> Any:
        status = self.evaluate_confluence(
            excel_j1, excel_j2, book_j1, book_j2, elo_j1, elo_j2, surface_j1, surface_j2
        )
        if status == "OK J1":
            won = (player_a == winner)
            record = BetRecord(
                f"{player_a} vs {player_b}", tournament, player_a,
                excel_j1, book_j1, won, self.stake_size
            )
            self.bets.append(record)
            return record
        elif status == "OK J2":
            won = (player_b == winner)
            record = BetRecord(
                f"{player_a} vs {player_b}", tournament, player_b,
                excel_j2, book_j2, won, self.stake_size
            )
            self.bets.append(record)
            return record
        return None

    def _check_value_bet(
        self,
        player_a: str,
        player_b: str,
        tournament: str,
        candidate: str,
        model_odds: float,
        market_odds: float,
        winner: str
    ) -> Any:
        if model_odds <= 1.01 or market_odds <= 1.01:
            return None

        prob_model = 1.0 / model_odds
        prob_market = 1.0 / market_odds
        edge = prob_model - prob_market

        if edge >= self.value_edge_threshold:
            match_name = f"{player_a} vs {player_b}"
            won = (candidate == winner)
            return BetRecord(
                match_name, tournament, candidate, model_odds, market_odds, won, self.stake_size
            )
        return None

    def get_summary(self) -> Dict[str, Any]:
        total_bets = len(self.bets)
        if total_bets == 0:
            return {"total_bets": 0, "win_rate": 0.0, "total_pnl": 0.0, "roi": 0.0}

        wins = sum(1 for b in self.bets if b.won)
        total_staked = sum(b.stake for b in self.bets)
        total_pnl = round(sum(b.pnl for b in self.bets), 2)
        roi = round((total_pnl / total_staked) * 100, 2) if total_staked > 0 else 0.0
        win_rate = round((wins / total_bets) * 100, 2)

        return {
            "total_bets": total_bets,
            "wins": wins,
            "losses": total_bets - wins,
            "win_rate": win_rate,
            "total_staked": total_staked,
            "total_pnl": total_pnl,
            "roi_percent": roi
        }
