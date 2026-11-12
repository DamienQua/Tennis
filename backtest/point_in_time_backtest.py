"""
Point-in-Time Historical Tennis Backtester (Zero Look-Ahead Bias).

Computes rolling player statistics (12-month win %, surface win %, rank)
strictly prior to each match date, applies the user's confluence betting filter,
and evaluates financial return across historical archives (2022-2024).
"""

import os
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
import jaro
from backtest.strategy_evaluator import StrategyEvaluator, BetRecord
from backtest.historical_odds import HistoricalOddsProvider

class FastEloMatcher:
    """Fast indexed matcher for player ELO ratings."""

    def __init__(self, elo_text: str):
        self.exact_lookup: Dict[str, Tuple[float, float, float]] = {}
        self.raw_lines: List[Tuple[str, Tuple[float, float, float]]] = []
        self._parse(elo_text)
        self.cache: Dict[Tuple[str, str], float] = {}

    def _parse(self, elo_text: str) -> None:
        for line in elo_text.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            tokens = line_str.split()
            if len(tokens) < 4:
                continue
            try:
                hard = float(tokens[-3])
                clay = float(tokens[-2])
                grass = float(tokens[-1])
            except ValueError:
                continue

            name_tokens = tokens[:-3]
            full_name = " ".join(name_tokens).lower()
            first_name = name_tokens[0].lower()
            init = first_name[0]
            surname = " ".join(name_tokens[1:]).lower()
            last_word = name_tokens[-1].lower()

            ratings = (hard, clay, grass)
            self.raw_lines.append((full_name, ratings))
            self.exact_lookup[f"{last_word}_{init}"] = ratings
            if surname:
                self.exact_lookup[f"{surname}_{init}"] = ratings
                self.exact_lookup[f"{surname.replace('-', ' ')}_{init}"] = ratings

    def get_elo(self, player_archive_name: str, surface: str) -> float:
        """Returns historical Elo rating for player prior to match date."""
        cache_key = (player_archive_name, surface)
        if cache_key in self.cache:
            return self.cache[cache_key]

        rating = self._lookup_rating(player_archive_name, surface)
        self.cache[cache_key] = rating
        return rating

    def _lookup_rating(self, player_archive_name: str, surface: str) -> float:
        p_clean = player_archive_name.replace(".", "").strip().lower()
        parts = p_clean.split()
        if not parts:
            return 1500.0

        ratings = self._get_exact_ratings(parts)
        if ratings:
            return self._select_surface_rating(ratings, surface)

        return self._fuzzy_lookup_rating(p_clean, surface)

    def _get_exact_ratings(self, parts: List[str]) -> Optional[Tuple[float, float, float]]:
        if len(parts) < 2:
            return self.exact_lookup.get(f"{parts[0]}_")
        init = parts[-1][0]
        last_word = parts[-2]
        surname = " ".join(parts[:-1])
        return (
            self.exact_lookup.get(f"{last_word}_{init}")
            or self.exact_lookup.get(f"{surname}_{init}")
        )

    def _fuzzy_lookup_rating(self, p_clean: str, surface: str) -> float:
        for full_name, rating_tuple in self.raw_lines:
            if jaro.jaro_winkler_metric(p_clean, full_name) >= 0.85:
                return self._select_surface_rating(rating_tuple, surface)
        return 1500.0

    @staticmethod
    def _select_surface_rating(ratings: Tuple[float, float, float], surface: str) -> float:
        surf_lower = surface.lower()
        if "clay" in surf_lower:
            return ratings[1]
        if "grass" in surf_lower:
            return ratings[2]
        return ratings[0]

class PointInTimeStats:
    """Maintains player match history and computes pre-match statistics."""

    def __init__(self, matches_df: pd.DataFrame):
        self.player_history: Dict[str, List[Tuple[pd.Timestamp, str, bool]]] = {}
        self._build_index(matches_df)

    def _build_index(self, matches_df: pd.DataFrame) -> None:
        for _, row in matches_df.iterrows():
            match_date = pd.to_datetime(row["Date"])
            surface_name = str(row.get("Surface", "")).strip().lower()
            winner_name = str(row.get("Winner", "")).strip().lower()
            loser_name = str(row.get("Loser", "")).strip().lower()
            if winner_name:
                if winner_name not in self.player_history:
                    self.player_history[winner_name] = []
                self.player_history[winner_name].append((match_date, surface_name, True))
            if loser_name:
                if loser_name not in self.player_history:
                    self.player_history[loser_name] = []
                self.player_history[loser_name].append((match_date, surface_name, False))

    @staticmethod
    def _tally_history(
            history: List[Tuple[pd.Timestamp, str, bool]],
            match_date: pd.Timestamp,
            date_12m: pd.Timestamp,
            surf_clean: str
    ) -> Tuple[int, int, int, int]:
        w_12m, tot_12m = 0, 0
        w_surf, tot_surf = 0, 0
        for m_date, m_surf, is_win in history:
            if m_date >= match_date:
                continue
            if m_date >= date_12m:
                tot_12m += 1
                w_12m += int(is_win)
            if m_surf == surf_clean:
                tot_surf += 1
                w_surf += int(is_win)
        return w_12m, tot_12m, w_surf, tot_surf

    def get_player_stats_before(
            self,
            player_name: str,
            match_date: pd.Timestamp,
            surface: str
    ) -> Tuple[float, float, int]:
        """Compute rolling 12-month win %, surface win %, and match count before match_date."""
        p_clean = player_name.strip().lower()
        history = self.player_history.get(p_clean, [])
        if not history:
            return 50.0, 50.0, 0

        date_12m = match_date - timedelta(days=365)
        surf_clean = surface.strip().lower()

        w_12m, tot_12m, w_surf, tot_surf = self._tally_history(
            history, match_date, date_12m, surf_clean
        )

        pct_12m = round((w_12m / tot_12m) * 100, 2) if tot_12m > 0 else 50.0
        pct_surf = round((w_surf / tot_surf) * 100, 2) if tot_surf > 0 else 50.0

        return pct_12m, pct_surf, tot_12m

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

    @staticmethod
    def _estimate_model_odds(*args, **kwargs) -> Tuple[float, float]:
        """Estimate model odds based on player surface %, ranking, and recent form."""
        score_a = PointInTimeBacktest._calculate_score_a(
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
