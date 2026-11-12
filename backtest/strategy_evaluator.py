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
    """Stores betting prediction parameters, market odds, resolution, and P&L."""

    def __init__(
            self,
            match_name: str,
            tournament: str,
            bet_on: str,
            *args,
            **kwargs
    ):
        self.match_name = match_name
        self.tournament = tournament
        self.bet_on = bet_on
        self.model_odds = args[0] if len(args) > 0 else kwargs.get("model_odds", 0.0)
        self.market_odds = args[1] if len(args) > 1 else kwargs.get("market_odds", 0.0)
        self.won = args[2] if len(args) > 2 else kwargs.get("won", False)
        self.stake = args[3] if len(args) > 3 else kwargs.get("stake", 1.0)

    @property
    def pnl(self) -> float:
        """Calculates profit and loss for this bet record."""
        if self.won:
            return round(self.stake * (self.market_odds - 1), 2)
        return -round(self.stake, 2)

    def to_dict(self) -> Dict[str, Any]:
        """Converts bet record to dictionary representation."""
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

def _parse_confluence_metrics(args: tuple):
    return (
        _to_float(args[0]), _to_float(args[1]),
        _to_float(args[2]), _to_float(args[3]),
        _to_float(args[4]), _to_float(args[5]),
        _to_float(args[6]), _to_float(args[7])
    )

class StrategyEvaluator:
    """Evaluates betting performance across a collection of match predictions."""

    def __init__(self, value_edge_threshold: float = 0.05, stake_size: float = 1.0):
        self.value_edge_threshold = value_edge_threshold
        self.stake_size = stake_size
        self.bets: List[BetRecord] = []

    @staticmethod
    def _is_ok_j1(*args, **kwargs) -> bool:
        ej1, ej2, bj1, bj2, el1, el2, surf_1, surf_2 = _parse_confluence_metrics(args)
        return ej1 < ej2 and bj1 < bj2 and el1 > el2 and surf_1 > surf_2 and bj1 > ej1

    @staticmethod
    def _is_ok_j2(*args, **kwargs) -> bool:
        ej1, ej2, bj1, bj2, el1, el2, surf_1, surf_2 = _parse_confluence_metrics(args)
        return ej1 > ej2 and bj1 > bj2 and el1 < el2 and surf_1 < surf_2 and bj2 > ej2

    @classmethod
    def evaluate_confluence(cls, *args, **kwargs) -> str:
        """Evaluates user model confluence criteria across players."""
        if cls._is_ok_j1(*args, **kwargs):
            return "OK J1"
        if cls._is_ok_j2(*args, **kwargs):
            return "OK J2"
        return "PAS OK"

    @classmethod
    def evaluate_alpha_5_plus(cls, *args, **kwargs) -> Dict[str, Any]:
        """Evaluates Alpha 5+ value betting criteria for a match."""
        return evaluate_alpha_strategy(*args, **kwargs)

    @classmethod
    def evaluate_optimized_confluence(cls, *args, surface: str = "Clay", **kwargs) -> str:
        """Evaluates optimized confluence strategy with surface thresholds."""
        s_clean = surface.lower()
        if "grass" in s_clean:
            return "PAS OK"

        raw = cls.evaluate_confluence(*args[:8], **kwargs)
        if raw == "PAS OK":
            return "PAS OK"

        elo_j1 = args[4]
        elo_j2 = args[5]
        book_j1 = args[2]
        book_j2 = args[3]
        elo_diff = abs(_to_float(elo_j1) - _to_float(elo_j2))
        bet_odds = _to_float(book_j1) if raw == "OK J1" else _to_float(book_j2)

        if "clay" in s_clean:
            return raw if elo_diff >= 50.0 else "PAS OK"
        if "hard" in s_clean:
            return raw if (elo_diff >= 120.0 and bet_odds <= 1.50) else "PAS OK"

        return "PAS OK"

    def evaluate_match_confluence(self, *args, **kwargs) -> Any:
        """Evaluates confluence and appends winning bet record if signal met."""
        player_a = args[0]
        player_b = args[1]
        tournament = args[2]
        excel_j1 = args[3]
        excel_j2 = args[4]
        book_j1 = args[5]
        book_j2 = args[6]
        winner = args[11]

        status = self.evaluate_confluence(*args[3:11], **kwargs)
        if status == "OK J1":
            won = (player_a == winner)
            record = BetRecord(
                f"{player_a} vs {player_b}", tournament, player_a,
                excel_j1, book_j1, won, self.stake_size
            )
            self.bets.append(record)
            return record
        if status == "OK J2":
            won = (player_b == winner)
            record = BetRecord(
                f"{player_a} vs {player_b}", tournament, player_b,
                excel_j2, book_j2, won, self.stake_size
            )
            self.bets.append(record)
            return record
        return None

    def _check_value_bet(self, *args, **kwargs) -> Any:
        player_a = args[0]
        player_b = args[1]
        tournament = args[2]
        candidate = args[3]
        model_odds = args[4]
        market_odds = args[5]
        winner = args[6]

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
        """Computes aggregate backtest betting metrics including win rate and ROI."""
        total_bets = len(self.bets)
        if total_bets == 0:
            return {"total_bets": 0, "win_rate": 0.0, "total_pnl": 0.0, "roi": 0.0}

        wins = sum(1 for bet_item in self.bets if bet_item.won)
        total_staked = sum(bet_item.stake for bet_item in self.bets)
        total_pnl = round(sum(bet_item.pnl for bet_item in self.bets), 2)
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
