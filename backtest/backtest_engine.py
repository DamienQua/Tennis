"""
Backtest engine for historical tennis matches.

Executes model analysis on historical matches, injects real historical closing odds,
evaluates value betting performance, and generates summary reports.
"""

import os
import asyncio
from typing import List, Dict, Any, Optional
import pandas as pd
from backtest.historical_odds import HistoricalOddsProvider
from backtest.strategy_evaluator import StrategyEvaluator, BetRecord

class BacktestResult:
    def __init__(self, match_url: str, match_data: Dict[str, Any], bets: List[BetRecord]):
        self.match_url = match_url
        self.match_data = match_data
        self.bets = bets

class BacktestEngine:
    """Coordinates historical match execution and strategy evaluation."""

    def __init__(
        self,
        historical_odds: Optional[HistoricalOddsProvider] = None,
        evaluator: Optional[StrategyEvaluator] = None,
        output_dir: str = "backtest/results"
    ):
        self.odds_provider = historical_odds or HistoricalOddsProvider()
        self.evaluator = evaluator or StrategyEvaluator()
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.results: List[BacktestResult] = []

    def process_match_result(
        self,
        match_url: str,
        player_a: str,
        player_b: str,
        tournament: str,
        model_odds_a: float,
        model_odds_b: float,
        elo_a: float = 0.0,
        elo_b: float = 0.0,
        surface_a: float = 0.0,
        surface_b: float = 0.0,
        year: int = 2023,
        gender: str = "atp"
    ) -> Optional[BacktestResult]:
        hist = self.odds_provider.get_match_odds(player_a, player_b, year, gender)
        if not hist:
            return None

        market_a = float(hist["odds_a"].get("b365") or hist["odds_a"].get("ps") or 0.0)
        market_b = float(hist["odds_b"].get("b365") or hist["odds_b"].get("ps") or 0.0)
        winner = hist["winner"]

        bet = self.evaluator.evaluate_match_confluence(
            player_a,
            player_b,
            tournament,
            model_odds_a,
            model_odds_b,
            market_a,
            market_b,
            elo_a,
            elo_b,
            surface_a,
            surface_b,
            winner
        )
        bets = [bet] if bet else []

        status = self.evaluator.evaluate_confluence(
            model_odds_a, model_odds_b, market_a, market_b, elo_a, elo_b, surface_a, surface_b
        )

        match_info = {
            "match_url": match_url,
            "tournament": tournament,
            "date": hist.get("date", ""),
            "player_a": player_a,
            "player_b": player_b,
            "excel_j1": model_odds_a,
            "excel_j2": model_odds_b,
            "book_j1": market_a,
            "book_j2": market_b,
            "elo_j1": elo_a,
            "elo_j2": elo_b,
            "surface_j1": surface_a,
            "surface_j2": surface_b,
            "confluence": status,
            "winner": winner
        }
        res = BacktestResult(match_url, match_info, bets)
        self.results.append(res)
        return res

    def export_summary(self, filename: str = "backtest_summary.xlsx") -> str:
        summary = self.evaluator.get_summary()
        bets_data = [b.to_dict() for b in self.evaluator.bets]
        matches_data = [r.match_data for r in self.results]

        filepath = os.path.join(self.output_dir, filename)
        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            pd.DataFrame([summary]).to_excel(writer, sheet_name="Summary", index=False)
            if bets_data:
                pd.DataFrame(bets_data).to_excel(writer, sheet_name="Bets", index=False)
            if matches_data:
                pd.DataFrame(matches_data).to_excel(writer, sheet_name="Matches", index=False)

        return filepath
