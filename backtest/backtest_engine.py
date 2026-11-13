"""Moteur d'exécution de backtest historique avec injection des cotes de clôture."""

import os
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from backtest.historical_odds import HistoricalOddsProvider
from backtest.strategy_evaluator import BetRecord, StrategyEvaluator
from utils.helpers import get_arg


class BacktestResult:
    """Résultat de simulation et paris déclenchés pour un match."""

    def __init__(
        self, match_url: str, match_data: Dict[str, Any], bets: List[BetRecord]
    ) -> None:
        self.match_url = match_url
        self.match_data = match_data
        self.bets = bets


def print_backtest_summary(
    summary: Dict[str, Any],
    total_matches: int,
    saved_path: str,
    title: str = "BILAN CONSOLIDÉ",
) -> None:
    """Affiche le bilan consolidé des performances du backtest."""
    print("\n" + "=" * 60)
    print(f"{title}")
    print(f"Total Matchs Analysés : {total_matches}")
    print(f"Total Paris Déclenchés  : {summary['total_bets']}")
    print(f"Paris Gagnés / Perdus   : {summary['wins']} / {summary['losses']}")
    print(f"Taux de Réussite        : {summary['win_rate']}%")
    print(f"P&L Total               : {summary['total_pnl']} unités")
    print(f"ROI                     : {summary['roi_percent']}%")
    print(f"Rapport consolidé dans  : {saved_path}")
    print("=" * 60 + "\n")


class BacktestEngine:
    """Coordonne l'évaluation historique des matchs et l'export Excel."""

    def __init__(
        self,
        historical_odds: Optional[HistoricalOddsProvider] = None,
        evaluator: Optional[StrategyEvaluator] = None,
        output_dir: str = "backtest/results",
        strategy_mode: str = "confluence",
    ) -> None:
        self.odds_provider = historical_odds or HistoricalOddsProvider()
        self.evaluator = evaluator or StrategyEvaluator()
        self.output_dir = output_dir
        self.strategy_mode = strategy_mode
        os.makedirs(self.output_dir, exist_ok=True)
        self.results: List[BacktestResult] = []

    @staticmethod
    def _parse_match_params(args: tuple, kwargs: dict) -> dict:
        return {
            "match_url": args[0],
            "player_a": args[1],
            "player_b": args[2],
            "tournament": args[3],
            "model_odds_a": args[4],
            "model_odds_b": args[5],
            "elo_a": get_arg(args, 6, kwargs.get("elo_a", 0.0)),
            "elo_b": get_arg(args, 7, kwargs.get("elo_b", 0.0)),
            "surface_a": get_arg(args, 8, kwargs.get("surface_a", 0.0)),
            "surface_b": get_arg(args, 9, kwargs.get("surface_b", 0.0)),
            "year": get_arg(args, 10, kwargs.get("year", 2023)),
            "gender": get_arg(args, 11, kwargs.get("gender", "atp")),
        }

    @staticmethod
    def _extract_closing_odds(hist: dict) -> Tuple[float, float]:
        m_a = float(hist["odds_a"].get("b365") or hist["odds_a"].get("ps") or 0.0)
        m_b = float(hist["odds_b"].get("b365") or hist["odds_b"].get("ps") or 0.0)
        return m_a, m_b

    def _evaluate_strategy(
        self, params: dict, m_a: float, m_b: float, winner: str
    ) -> Tuple[str, List[BetRecord]]:
        if self.strategy_mode == "alpha_5_plus":
            bet = self.evaluator.evaluate_match_alpha_5_plus(
                params["player_a"],
                params["player_b"],
                params["tournament"],
                params["model_odds_a"],
                params["model_odds_b"],
                m_a,
                m_b,
                params["elo_a"],
                params["elo_b"],
                winner,
            )
            status = f"ALPHA 5+ ({bet.bet_on})" if bet else "PAS OK"
            return status, ([bet] if bet else [])

        bet = self.evaluator.evaluate_match_confluence(
            params["player_a"],
            params["player_b"],
            params["tournament"],
            params["model_odds_a"],
            params["model_odds_b"],
            m_a,
            m_b,
            params["elo_a"],
            params["elo_b"],
            params["surface_a"],
            params["surface_b"],
            winner,
        )
        status = self.evaluator.evaluate_confluence(
            params["model_odds_a"],
            params["model_odds_b"],
            m_a,
            m_b,
            params["elo_a"],
            params["elo_b"],
            params["surface_a"],
            params["surface_b"],
        )
        return status, ([bet] if bet else [])

    @classmethod
    def _build_match_record(
        cls, params: dict, hist: dict, status: str, bets: list
    ) -> BacktestResult:
        market_a, market_b = cls._extract_closing_odds(hist)
        match_info = {
            "match_url": params["match_url"],
            "tournament": params["tournament"],
            "date": hist.get("date", ""),
            "player_a": params["player_a"],
            "player_b": params["player_b"],
            "excel_j1": params["model_odds_a"],
            "excel_j2": params["model_odds_b"],
            "book_j1": market_a,
            "book_j2": market_b,
            "elo_j1": params["elo_a"],
            "elo_j2": params["elo_b"],
            "surface_j1": params["surface_a"],
            "surface_j2": params["surface_b"],
            "confluence": status,
            "winner": hist["winner"],
        }
        return BacktestResult(params["match_url"], match_info, bets)

    def process_match_result(self, *args, **kwargs) -> Optional[BacktestResult]:
        """Injecte les cotes historiques, évalue la stratégie et enregistre le résultat."""
        params = self._parse_match_params(args, kwargs)
        hist = self.odds_provider.get_match_odds(
            params["player_a"], params["player_b"], params["year"], params["gender"]
        )
        if not hist:
            return None

        m_a, m_b = self._extract_closing_odds(hist)
        status, bets = self._evaluate_strategy(params, m_a, m_b, hist["winner"])
        res = self._build_match_record(params, hist, status, bets)
        self.results.append(res)
        return res

    def export_summary(self, filename: str = "backtest_summary.xlsx") -> str:
        """Exporte le bilan, les paris et les matchs vers un classeur Excel."""
        summary = self.evaluator.get_summary()
        bets_data = [bet_item.to_dict() for bet_item in self.evaluator.bets]
        matches_data = [res_item.match_data for res_item in self.results]

        filepath = os.path.join(self.output_dir, filename)
        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            pd.DataFrame([summary]).to_excel(writer, sheet_name="Summary", index=False)
            if bets_data:
                pd.DataFrame(bets_data).to_excel(writer, sheet_name="Bets", index=False)
            if matches_data:
                pd.DataFrame(matches_data).to_excel(writer, sheet_name="Matches", index=False)
        return filepath