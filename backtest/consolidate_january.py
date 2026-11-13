"""Consolidation des fiches Excel générées dans Matchs/2023/January/."""

import asyncio
import glob
import os
import sys
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import openpyxl
from backtest.backtest_engine import BacktestEngine, print_backtest_summary
from backtest.historical_odds import HistoricalOddsProvider
from backtest.strategy_evaluator import StrategyEvaluator
from data_providers.elo_matcher import EloMatcher
from data_providers.elo_table import elo_table


def _extract_match_data(worksheet: Any) -> Optional[Dict[str, Any]]:
    player1 = worksheet.cell(1, 2).value
    player2 = worksheet.cell(1, 3).value
    if not player1 or not player2:
        return None
    return {
        "p1": str(player1),
        "p2": str(player2),
        "surf_1": float(worksheet.cell(4, 2).value or 0.0),
        "surf_2": float(worksheet.cell(4, 3).value or 0.0),
        "odds_1": float(worksheet.cell(24, 2).value or 0.0),
        "odds_2": float(worksheet.cell(24, 3).value or 0.0),
    }


def _process_file(
    filepath: str, tour_name: str, gender: str, elo_data: str, engine: BacktestEngine
) -> None:
    try:
        workbook = openpyxl.load_workbook(filepath, data_only=True)
        data = _extract_match_data(workbook.active)
        if not data:
            return

        elo_1_str, elo_2_str = EloMatcher.find_elo_ratings(
            elo_data, data["p1"], data["p2"], "Hard"
        )
        elo_1 = float(elo_1_str) if elo_1_str and elo_1_str.replace(".", "", 1).isdigit() else 0.0
        elo_2 = float(elo_2_str) if elo_2_str and elo_2_str.replace(".", "", 1).isdigit() else 0.0

        engine.process_match_result(
            filepath,
            data["p1"],
            data["p2"],
            tour_name,
            data["odds_1"],
            data["odds_2"],
            elo_a=elo_1,
            elo_b=elo_2,
            surface_a=data["surf_1"],
            surface_b=data["surf_2"],
            year=2023,
            gender=gender,
        )
    except (OSError, KeyError, ValueError, TypeError, IndexError):
        pass


def _process_tournament(
    tour_dir: str, atp_elo: str, wta_elo: str, engine: BacktestEngine
) -> int:
    tour_name = os.path.basename(tour_dir).replace("_", " ")
    gender = "wta" if "wta" in tour_name.lower() else "atp"
    elo_data = wta_elo if gender == "wta" else atp_elo
    xlsx_files = glob.glob(os.path.join(tour_dir, "*.xlsx"))

    print(f"\nProcessing {tour_name}: {len(xlsx_files)} match files")
    for filepath in xlsx_files:
        _process_file(filepath, tour_name, gender, elo_data, engine)
    return len(xlsx_files)


async def consolidate_january(strategy_mode: str = "alpha_5_plus") -> None:
    """Consolide les résultats de janvier 2023 dans un rapport Excel unique."""
    base_dir = "Matchs/2023/January"
    tour_folders = [
        folder for folder in glob.glob(os.path.join(base_dir, "*")) if os.path.isdir(folder)
    ]

    engine = BacktestEngine(
        historical_odds=HistoricalOddsProvider(),
        evaluator=StrategyEvaluator(),
        output_dir="backtest/results",
        strategy_mode=strategy_mode,
    )

    atp_elo, wta_elo = await asyncio.gather(elo_table("ATP"), elo_table("WTA"))
    print(f"Consolidating backtest results from {len(tour_folders)} tournaments...")

    for tour_dir in tour_folders:
        _process_tournament(tour_dir, atp_elo, wta_elo, engine)

    summary = engine.evaluator.get_summary()
    saved_path = engine.export_summary("january_2023_consolidated_backtest.xlsx")
    print_backtest_summary(
        summary, len(engine.results), saved_path,
        title="BILAN CONSOLIDÉ - JANVIER 2023 (TOUS TOURNOIS)",
    )


if __name__ == "__main__":
    asyncio.run(consolidate_january())