"""Backtester historique chronologiquement pur aligné sur analysis.compare_players."""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from analysis.compare_players import compare_players
from backtest.point_in_time_stats import PointInTimeStats
from backtest.strategy_evaluator import StrategyEvaluator
from core.models import MatchAnalysisData, PlayerStats
from utils.helpers import safe_float, safe_int

logger = logging.getLogger(__name__)


class PointInTimeBacktester:
    """Exécute des simulations historiques sans biais temporel avec le modèle de production."""

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

    def run_backtest_for_year(
        self, year: int, gender: str, elo_data: str = ""
    ) -> Dict[str, Any]:
        """Exécute le backtest point-in-time sur une saison complète (zéro look-ahead bias)."""
        if elo_data:
            logger.info(
                "Paramètre elo_data ignoré en mode point-in-time pour éviter tout look-ahead bias."
            )
        combined_df = self._load_historical_dataset(gender)
        filepath = os.path.join(self.data_dir, f"{gender}_{year}.xlsx")
        if combined_df.empty or not os.path.exists(filepath):
            return {"error": "Dataset empty or missing"}

        stats_engine = PointInTimeStats(combined_df)
        target_raw = pd.read_excel(filepath)
        target_raw["Date"] = pd.to_datetime(target_raw["Date"])
        target_df = target_raw[target_raw["Comment"] == "Completed"].sort_values("Date")

        logger.info(
            "Running Point-in-Time backtest (%s) for %s %d (%d matches)...",
            self.strategy_mode,
            gender.upper(),
            year,
            len(target_df),
        )

        for _, row in target_df.iterrows():
            self._process_single_row(row, stats_engine)

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
                parsed = safe_float(val, default=0.0)
                if parsed > 0:
                    return parsed
        return 0.0

    def _build_point_in_time_match(
        self, row: pd.Series, stats_engine: PointInTimeStats
    ) -> Tuple[MatchAnalysisData, pd.Timestamp]:
        p_w, p_l = str(row["Winner"]), str(row["Loser"])
        match_date = pd.to_datetime(row["Date"])
        surface = str(row.get("Surface", "Hard"))
        tour = str(row.get("Tournament", ""))

        prof_w = stats_engine.get_player_profile_before(p_w, match_date, surface)
        prof_l = stats_engine.get_player_profile_before(p_l, match_date, surface)
        elo_w = stats_engine.get_player_elo_before(p_w, match_date, surface)
        elo_l = stats_engine.get_player_elo_before(p_l, match_date, surface)
        h2h = stats_engine.get_h2h_before(p_w, p_l, match_date, surface)

        rank_w = safe_int(row.get("WRank"), default=200) or 200
        rank_l = safe_int(row.get("LRank"), default=200) or 200
        book_w = self._get_val(row, "PSW", "B365W")
        book_l = self._get_val(row, "PSL", "B365L")

        match_obj = MatchAnalysisData(
            match_url="",
            tournament=tour,
            surface=surface,
            player_a=PlayerStats(
                name=p_w,
                ranking=rank_w,
                elo=elo_w,
                book_odds=book_w,
                win_pct_last_10=prof_w["win_pct_last_10"],
                win_pct_last_50=prof_w["win_pct_last_50"],
                win_pct_1y=prof_w["win_pct_1y"],
                win_pct_career=prof_w["win_pct_career"],
                win_pct_1y_surface=prof_w["win_pct_1y_surface"],
                win_pct_career_surface=prof_w["win_pct_career_surface"],
                matches_last_month=int(prof_w["matches_last_month"]),
            ),
            player_b=PlayerStats(
                name=p_l,
                ranking=rank_l,
                elo=elo_l,
                book_odds=book_l,
                win_pct_last_10=prof_l["win_pct_last_10"],
                win_pct_last_50=prof_l["win_pct_last_50"],
                win_pct_1y=prof_l["win_pct_1y"],
                win_pct_career=prof_l["win_pct_career"],
                win_pct_1y_surface=prof_l["win_pct_1y_surface"],
                win_pct_career_surface=prof_l["win_pct_career_surface"],
                matches_last_month=int(prof_l["matches_last_month"]),
            ),
            h2h=h2h,
        )
        compare_players(match_obj)
        return match_obj, match_date

    def _evaluate_match(self, match_obj: MatchAnalysisData) -> Tuple[str, Any]:
        pa, pb = match_obj.player_a, match_obj.player_b
        if self.strategy_mode == "alpha_5_plus":
            bet = self.evaluator.evaluate_match_alpha_5_plus(
                pa.name,
                pb.name,
                match_obj.tournament,
                pa.model_odds,
                pb.model_odds,
                pa.book_odds,
                pb.book_odds,
                pa.elo,
                pb.elo,
                pa.name,
            )
            return (f"ALPHA 5+ ({bet.bet_on})" if bet else "PAS OK"), bet

        bet = self.evaluator.evaluate_match_confluence(
            pa.name,
            pb.name,
            match_obj.tournament,
            pa.model_odds,
            pb.model_odds,
            pa.book_odds,
            pb.book_odds,
            pa.elo,
            pb.elo,
            pa.win_pct_career_surface,
            pb.win_pct_career_surface,
            pa.name,
        )
        status = self.evaluator.evaluate_confluence(
            pa.model_odds,
            pb.model_odds,
            pa.book_odds,
            pb.book_odds,
            pa.elo,
            pb.elo,
            pa.win_pct_career_surface,
            pb.win_pct_career_surface,
        )
        return status, bet

    def _process_single_row(
        self, row: pd.Series, stats_engine: PointInTimeStats
    ) -> None:
        match_obj, match_date = self._build_point_in_time_match(row, stats_engine)
        pa, pb = match_obj.player_a, match_obj.player_b
        status, bet = self._evaluate_match(match_obj)
        self.records.append({
            "date": match_date.strftime("%Y-%m-%d"),
            "tournament": match_obj.tournament,
            "surface": match_obj.surface,
            "winner": pa.name,
            "loser": pb.name,
            "model_w": pa.model_odds,
            "model_l": pb.model_odds,
            "book_w": pa.book_odds,
            "book_l": pb.book_odds,
            "elo_w": pa.elo,
            "elo_l": pb.elo,
            "surf_w": pa.win_pct_career_surface,
            "surf_l": pb.win_pct_career_surface,
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
