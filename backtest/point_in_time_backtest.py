"""Backtester historique chronologiquement pur (zéro look-ahead bias)."""

import os
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from backtest.fast_elo_matcher import FastEloMatcher
from backtest.point_in_time_stats import PointInTimeStats
from backtest.strategy_evaluator import StrategyEvaluator


class PointInTimeBacktester:
    """Exécute des simulations historiques sans biais temporel."""

    def __init__(
        self,
        data_dir: str = "backtest/data",
        evaluator: Optional[StrategyEvaluator] = None,
        output_dir: str = "backtest/results",
        strategy_mode: str = "alpha_5_plus",
    ) -> None:
        self.data_dir = data_dir
        self.evaluator = evaluator or StrategyEvaluator()
        self.output_dir = output_dir
        self.strategy_mode = strategy_mode
        os.makedirs(self.output_dir, exist_ok=True)
        self.records: List[Dict[str, Any]] = []

    def _load_historical_dataset(self, gender: str) -> pd.DataFrame:
        dfs = []
        for year in (2022, 2023, 2024, 2025, 2026):
            filepath = os.path.join(self.data_dir, f"{gender}_{year}.xlsx")
            if os.path.exists(filepath):
                dfs.append(pd.read_excel(filepath))
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
        form_b: float,
    ) -> float:
        diff_surf = (surf_a - surf_b) * 0.4
        diff_form = (form_a - form_b) * 0.3
        r_a = max(1.0, rank_a if rank_a > 0 else 200.0)
        r_b = max(1.0, rank_b if rank_b > 0 else 200.0)
        diff_rank = (r_b - r_a) / max(r_a, r_b) * 30.0
        score_a = 50.0 + diff_surf + diff_form + diff_rank
        return max(5.0, min(95.0, score_a))

    @classmethod
    def _estimate_model_odds(
        cls,
        surf_a: float,
        surf_b: float,
        rank_a: float,
        rank_b: float,
        form_a: float,
        form_b: float,
    ) -> Tuple[float, float]:
        score_a = cls._calculate_score_a(surf_a, surf_b, rank_a, rank_b, form_a, form_b)
        return round(90.0 / score_a, 2), round(90.0 / (100.0 - score_a), 2)

    def run_backtest_for_year(
        self, year: int, gender: str, elo_data: str = ""
    ) -> Dict[str, Any]:
        """Exécute le backtest point-in-time sur une saison complète."""
        combined_df = self._load_historical_dataset(gender)
        filepath = os.path.join(self.data_dir, f"{gender}_{year}.xlsx")
        if combined_df.empty or not os.path.exists(filepath):
            return {"error": "Dataset empty or missing"}

        stats_engine = PointInTimeStats(combined_df)
        fallback_elo = FastEloMatcher(elo_data) if elo_data else None

        target_raw = pd.read_excel(filepath)
        target_raw["Date"] = pd.to_datetime(target_raw["Date"])
        target_df = target_raw[target_raw["Comment"] == "Completed"].sort_values("Date")

        print(
            f"Running Point-in-Time backtest ({self.strategy_mode}) for "
            f"{gender.upper()} {year} ({len(target_df)} matches)..."
        )

        for _, row in target_df.iterrows():
            self._process_single_row(row, stats_engine, fallback_elo)

        summary = self.evaluator.get_summary()
        filename = f"point_in_time_{gender}_{year}_{self.strategy_mode}_backtest.xlsx"
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
                    return float(val)
                except ValueError:
                    pass
        return 0.0

    def _extract_row_features(
        self,
        row: pd.Series,
        stats_engine: PointInTimeStats,
        fallback_elo: Optional[FastEloMatcher],
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
        if elo_w == 1500.0 and elo_l == 1500.0 and fallback_elo is not None:
            elo_w = fallback_elo.get_elo(p_w, surface)
            elo_l = fallback_elo.get_elo(p_l, surface)

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
        fallback_elo: Optional[FastEloMatcher],
    ) -> None:
        feat = self._extract_row_features(row, stats_engine, fallback_elo)
        odds_w, odds_l = self._estimate_model_odds(
            feat["surf_w"],
            feat["surf_l"],
            feat["rank_w"],
            feat["rank_l"],
            feat["form_w"],
            feat["form_l"],
        )
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