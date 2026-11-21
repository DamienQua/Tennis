"""Backtester historique chronologiquement pur (zéro look-ahead bias)."""

import os
from math import isfinite
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from analysis.probability_model import build_features, load_model, model_odds
from backtest.point_in_time_stats import PointInTimeStats, completed_matches
from backtest.strategy_evaluator import StrategyEvaluator
from backtest.historical_odds import HistoricalOddsProvider


class PointInTimeBacktester:
    """Exécute des simulations historiques sans biais temporel."""

    def __init__(
        self,
        data_dir: str = "backtest/data",
        evaluator: Optional[StrategyEvaluator] = None,
        output_dir: str = "backtest/results",
        strategy_mode: str = "alpha_5_plus",
        model_path: Optional[str] = None,
    ) -> None:
        self.data_dir = data_dir
        self.evaluator = evaluator or StrategyEvaluator()
        self.output_dir = output_dir
        self.strategy_mode = strategy_mode
        self.model = load_model(model_path)
        os.makedirs(self.output_dir, exist_ok=True)
        self.records: List[Dict[str, Any]] = []

    def _load_historical_dataset(self, gender: str) -> pd.DataFrame:
        dfs = []
        from pathlib import Path
        for filepath in sorted(Path(self.data_dir).glob(f"{gender.lower()}_[0-9][0-9][0-9][0-9].xlsx")):
            dfs.append(pd.read_excel(filepath))
        if not dfs:
            return pd.DataFrame()
        combined = pd.concat(dfs, ignore_index=True)
        return completed_matches(combined)

    @staticmethod
    def _estimate_model_odds(
        surf_a: float,
        surf_b: float,
        rank_a: float,
        rank_b: float,
        form_a: float,
        form_b: float,
        elo_a: float,
        elo_b: float,
        surface: str = "Hard",
        model: Optional[dict] = None,
        as_of: Any = None,
    ) -> Tuple[float, float]:
        features = build_features(rank_a, rank_b, form_a, form_b, surf_a, surf_b, elo_a, elo_b)
        return model_odds(features, surface, model, as_of)

    def run_backtest_for_year(
        self, year: int, gender: str, elo_data: str = "", *,
        tournament: Optional[str] = None, month: Optional[int] = None,
        report_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Exécute le backtest point-in-time sur une saison complète."""
        if elo_data:
            raise ValueError("Historical backtests reject undated external ELO data")
        gender = gender.lower()
        if gender not in {"atp", "wta"}:
            raise ValueError("Circuit must be atp or wta")
        self.records.clear()
        self.evaluator.bets.clear()
        combined_df = self._load_historical_dataset(gender)
        filepath = os.path.join(self.data_dir, f"{gender}_{year}.xlsx")
        if combined_df.empty or not os.path.exists(filepath):
            return {"error": "Dataset empty or missing"}

        stats_engine = PointInTimeStats(combined_df)

        target_raw = pd.read_excel(filepath)
        target_df = completed_matches(target_raw)
        target_df = target_df[target_df["Date"].dt.year == year]
        if tournament is not None:
            target_df = target_df[target_df["Tournament"].astype(str).str.casefold() == tournament.strip().casefold()]
        if month is not None:
            target_df = target_df[target_df["Date"].dt.month == month]
        if target_df.empty:
            return {"error": "No local matches for the requested year, tournament or month"}

        print(
            f"Running Point-in-Time backtest ({self.strategy_mode}) for "
            f"{gender.upper()} {year} ({len(target_df)} matches)..."
        )

        for _, row in target_df.iterrows():
            self._process_single_row(row, stats_engine)

        summary = self.evaluator.get_summary()
        eligible = sum(record["model_w"] > 1 and record["model_l"] > 1 for record in self.records)
        summary.update(total_matches=len(self.records), model_eligible=eligible,
                       skipped_missing_features=len(self.records) - eligible)
        filename = report_name or f"point_in_time_{gender}_{year}_{self.strategy_mode}_backtest.xlsx"
        self._export_results(filename, summary)
        return summary

    @staticmethod
    def _get_val(row: pd.Series, primary: str, fallback: Optional[str] = None) -> float:
        for col in (primary, fallback):
            if not col:
                continue
            val = row.get(col)
            if pd.notna(val) and val:
                try:
                    parsed = float(val)
                    if isfinite(parsed) and parsed > 0:
                        return parsed
                except (ValueError, TypeError):
                    pass
        return 0.0

    def _extract_row_features(
        self,
        row: pd.Series,
        stats_engine: PointInTimeStats,
    ) -> dict:
        p_w, p_l = str(row["Winner"]), str(row["Loser"])
        match_date = pd.to_datetime(row["Date"])
        surface = str(row.get("Surface", "Hard"))
        tour = str(row.get("Tournament", ""))
        form_w, surf_w, _ = stats_engine.get_player_stats_before(p_w, match_date, surface)
        form_l, surf_l, _ = stats_engine.get_player_stats_before(p_l, match_date, surface)

        # Priorité à l'ELO historique glissant (zéro look-ahead bias)
        elo_w = stats_engine.get_player_elo_before(p_w, match_date, surface)
        elo_l = stats_engine.get_player_elo_before(p_l, match_date, surface)
        book_w, book_l = HistoricalOddsProvider._extract_market_odds(row, "PS")
        if not book_w:
            book_w, book_l = HistoricalOddsProvider._extract_market_odds(row, "B365")

        return {
            "p_w": p_w,
            "p_l": p_l,
            "match_date": match_date,
            "surface": surface,
            "tour": tour,
            "surf_w": surf_w,
            "surf_l": surf_l,
            "form_w": form_w,
            "form_l": form_l,
            "rank_w": self._get_val(row, "WRank"),
            "rank_l": self._get_val(row, "LRank"),
            "book_w": book_w,
            "book_l": book_l,
            "elo_w": elo_w,
            "elo_l": elo_l,
        }

    def _evaluate_row(
        self, feat: dict, odds_w: float, odds_l: float
    ) -> Tuple[str, Any]:
        if self.strategy_mode == "alpha_5_plus":
            bet = self.evaluator.evaluate_match_alpha_5_plus(
                feat["p_w"],
                feat["p_l"],
                feat["tour"],
                odds_w,
                odds_l,
                feat["book_w"],
                feat["book_l"],
                feat["elo_w"],
                feat["elo_l"],
                feat["p_w"],
            )
            return (f"ALPHA 5+ ({bet.bet_on})" if bet else "PAS OK"), bet

        bet = self.evaluator.evaluate_match_confluence(
            feat["p_w"],
            feat["p_l"],
            feat["tour"],
            odds_w,
            odds_l,
            feat["book_w"],
            feat["book_l"],
            feat["elo_w"],
            feat["elo_l"],
            feat["surf_w"],
            feat["surf_l"],
            feat["p_w"],
        )
        status = self.evaluator.evaluate_confluence(
            odds_w,
            odds_l,
            feat["book_w"],
            feat["book_l"],
            feat["elo_w"],
            feat["elo_l"],
            feat["surf_w"],
            feat["surf_l"],
        )
        return status, bet

    def _process_single_row(
        self,
        row: pd.Series,
        stats_engine: PointInTimeStats,
    ) -> None:
        feat = self._extract_row_features(row, stats_engine)
        try:
            odds_w, odds_l = self._estimate_model_odds(
                feat["surf_w"], feat["surf_l"], feat["rank_w"], feat["rank_l"],
                feat["form_w"], feat["form_l"], feat["elo_w"], feat["elo_l"],
                feat["surface"], self.model, feat["match_date"],
            )
        except (ValueError, TypeError):
            odds_w, odds_l = 0.0, 0.0
        status, bet = self._evaluate_row(feat, odds_w, odds_l)
        self.records.append({
            "date": feat["match_date"].strftime("%Y-%m-%d"),
            "tournament": feat["tour"],
            "surface": feat["surface"],
            "winner": feat["p_w"],
            "loser": feat["p_l"],
            "model_w": odds_w,
            "model_l": odds_l,
            "book_w": feat["book_w"],
            "book_l": feat["book_l"],
            "elo_w": feat["elo_w"],
            "elo_l": feat["elo_l"],
            "surf_w": feat["surf_w"],
            "surf_l": feat["surf_l"],
            "strategy_signal": status,
            "bet_placed": bool(bet),
            "bet_won": getattr(bet, "won", None),
            "pnl": getattr(bet, "pnl", 0.0),
        })

    def _export_results(self, filename: str, summary: Dict[str, Any]) -> str:
        filepath = os.path.join(self.output_dir, filename)
        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            pd.DataFrame([summary]).to_excel(writer, sheet_name="Summary", index=False)
            if self.evaluator.bets:
                bets_data = [bet_item.to_dict() for bet_item in self.evaluator.bets]
                pd.DataFrame(bets_data).to_excel(writer, sheet_name="Bets", index=False)
            if self.records:
                pd.DataFrame(self.records).to_excel(writer, sheet_name="AllMatches", index=False)
        return filepath


PointInTimeBacktest = PointInTimeBacktester
