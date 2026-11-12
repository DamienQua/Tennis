"""
Point-in-Time Historical Tennis Backtester (Zero Look-Ahead Bias).

Computes rolling player statistics (12-month win %, surface win %, rank)
strictly prior to each match date, applies the user's confluence betting filter,
and evaluates financial return across historical archives (2022-2026).
"""

import os
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from backtest.fast_elo_matcher import FastEloMatcher
from backtest.point_in_time_stats import PointInTimeStats
from backtest.strategy_evaluator import BetRecord, StrategyEvaluator


class PointInTimeBacktester:
    """Executes chronologically pure backtesting on historical match datasets."""

    def __init__(
            self,
            data_dir: str = "backtest/data",
            evaluator: Optional[StrategyEvaluator] = None,
            output_dir: str = "backtest/results"
    ):
        self.data_dir = data_dir
        self.evaluator = evaluator or StrategyEvaluator()
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.records: List[Dict[str, Any]] = []

    def _load_historical_dataset(self, gender: str) -> pd.DataFrame:
        """Combine 2022-2026 data to ensure rolling windows are populated."""
        dfs = []
        for year in [2022, 2023, 2024, 2025, 2026]:
            filename = f"{gender}_{year}.xlsx"
            filepath = os.path.join(self.data_dir, filename)
            if os.path.exists(filepath):
                frame = pd.read_excel(filepath)
                dfs.append(frame)
        if not dfs:
            return pd.DataFrame()
        combined = pd.concat(dfs, ignore_index=True)
        combined["Date"] = pd.to_datetime(combined["Date"])
        combined.sort_values("Date", inplace=True)
        combined.reset_index(drop=True, inplace=True)
        return combined

    @staticmethod
    def _calculate_score_a(
            surf_a: float,
            surf_b: float,
            rank_a: float,
            rank_b: float,
            form_a: float,
            form_b: float
    ) -> float:
        """Calculates win probability score component for player A."""
        diff_surf = (surf_a - surf_b) * 0.4
        diff_form = (form_a - form_b) * 0.3
        r_a = max(1.0, rank_a if rank_a > 0 else 200.0)
        r_b = max(1.0, rank_b if rank_b > 0 else 200.0)
        diff_rank = (r_b - r_a) / max(r_a, r_b) * 30.0
        score_a = 50.0 + diff_surf + diff_form + diff_rank
        return max(5.0, min(95.0, score_a))

    @classmethod
    def _estimate_model_odds(cls, *args, **kwargs) -> Tuple[float, float]:
        """Estimate model odds based on player surface %, ranking, and recent form."""
        score_a = cls._calculate_score_a(
            args[0], args[1], args[2], args[3], args[4], args[5]
        )
        return round(90.0 / score_a, 2), round(90.0 / (100.0 - score_a), 2)

    def run_backtest_for_year(
            self,
            year: int,
            gender: str,
            elo_data: str
    ) -> Dict[str, Any]:
        """Executes point-in-time backtest across all matches of a season."""
        combined_df = self._load_historical_dataset(gender)
        filepath = os.path.join(self.data_dir, f"{gender}_{year}.xlsx")
        if combined_df.empty or not os.path.exists(filepath):
            return {"error": "Dataset empty or missing"}

        stats_engine = PointInTimeStats(combined_df)
        elo_matcher = FastEloMatcher(elo_data)

        target_raw = pd.read_excel(filepath)
        target_raw["Date"] = pd.to_datetime(target_raw["Date"])
        target_df = target_raw[target_raw["Comment"] == "Completed"].sort_values("Date")

        print(
            f"Running Point-in-Time backtest for {gender.upper()} {year} "
            f"({len(target_df)} matches)..."
        )

        for _, row in target_df.iterrows():
            self._process_single_row(row, stats_engine, elo_matcher)

        summary = self.evaluator.get_summary()
        filename = f"point_in_time_{gender}_{year}_backtest.xlsx"
        self._export_results(filename, summary)
        return summary

    @staticmethod
    def _get_val(row: pd.Series, primary: str, fallback: Optional[str] = None) -> float:
        val = row.get(primary)
        if pd.notna(val) and val:
            try:
                return float(val)
            except ValueError:
                pass
        if fallback:
            f_val = row.get(fallback)
            if pd.notna(f_val) and f_val:
                try:
                    return float(f_val)
                except ValueError:
                    pass
        return 0.0

    @staticmethod
    def _build_record(*args, **kwargs) -> Dict[str, Any]:
        info = args[0]
        models = args[1]
        books = args[2]
        elos = args[3]
        surfs = args[4]
        status = args[5]
        bet = args[6]
        return {
            "date": info["date"],
            "tournament": info["tour"],
            "surface": info["surface"],
            "winner": info["winner"],
            "loser": info["loser"],
            "model_w": models[0],
            "model_l": models[1],
            "book_w": books[0],
            "book_l": books[1],
            "elo_w": elos[0],
            "elo_l": elos[1],
            "surf_w": surfs[0],
            "surf_l": surfs[1],
            "confluence": status,
            "bet_placed": bool(bet),
            "bet_won": getattr(bet, "won", None),
            "pnl": getattr(bet, "pnl", 0.0)
        }

    def _extract_row_features(
            self,
            row: pd.Series,
            stats_engine: PointInTimeStats,
            elo_matcher: FastEloMatcher
    ) -> dict:
        """Extracts stats and odds features for a single match row."""
        p_w, p_l = str(row["Winner"]), str(row["Loser"])
        match_date = pd.to_datetime(row["Date"])
        surface = str(row.get("Surface", "Hard"))
        tour = str(row.get("Tournament", ""))
        form_w, surf_w, _ = stats_engine.get_player_stats_before(p_w, match_date, surface)
        form_l, surf_l, _ = stats_engine.get_player_stats_before(p_l, match_date, surface)
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
            "book_w": self._get_val(row, "PSW", "B365W"),
            "book_l": self._get_val(row, "PSL", "B365L"),
            "elo_w": elo_matcher.get_elo(p_w, surface),
            "elo_l": elo_matcher.get_elo(p_l, surface)
        }

    def _process_single_row(
            self,
            row: pd.Series,
            stats_engine: PointInTimeStats,
            elo_matcher: FastEloMatcher
    ) -> None:
        """Processes a single completed match row within backtest simulation."""
        features = self._extract_row_features(row, stats_engine, elo_matcher)
        odds_w, odds_l = self._estimate_model_odds(
            features["surf_w"], features["surf_l"], features["rank_w"],
            features["rank_l"], features["form_w"], features["form_l"]
        )
        bet = self.evaluator.evaluate_match_confluence(
            features["p_w"], features["p_l"], features["tour"], odds_w, odds_l,
            features["book_w"], features["book_l"], features["elo_w"],
            features["elo_l"], features["surf_w"], features["surf_l"], features["p_w"]
        )
        status = self.evaluator.evaluate_confluence(
            odds_w, odds_l,
            features["book_w"], features["book_l"],
            features["elo_w"], features["elo_l"],
            features["surf_w"], features["surf_l"]
        )
        info = {
            "date": features["match_date"].strftime("%Y-%m-%d"),
            "tour": features["tour"], "surface": features["surface"],
            "winner": features["p_w"], "loser": features["p_l"]
        }
        self.records.append(
            self._build_record(
                info,
                (odds_w, odds_l),
                (features["book_w"], features["book_l"]),
                (features["elo_w"], features["elo_l"]),
                (features["surf_w"], features["surf_l"]),
                status,
                bet
            )
        )

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
