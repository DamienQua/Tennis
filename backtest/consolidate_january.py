"""
Consolidation script for January 2023 backtest.
Reads all match spreadsheets generated in Matchs/2023/January/,
matches with historical closing odds, applies user confluence filter,
and exports the consolidated Excel report with full P&L and ROI.
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import glob
import asyncio
import openpyxl
import pandas as pd
from typing import Dict, Any, List, Optional
from backtest.historical_odds import HistoricalOddsProvider
from backtest.strategy_evaluator import StrategyEvaluator, BetRecord
from backtest.backtest_engine import BacktestResult, BacktestEngine
from data_providers.elo_matcher import EloMatcher
from data_providers.ELO_table import ELO_table

def _extract_match_data(ws: Any) -> Optional[Dict[str, Any]]:
    p1 = ws.cell(1, 2).value
    p2 = ws.cell(1, 3).value
    if not p1 or not p2:
        return None
    return {
        "p1": str(p1),
        "p2": str(p2),
        "surf_1": float(ws.cell(4, 2).value or 0.0),
        "surf_2": float(ws.cell(4, 3).value or 0.0),
        "odds_1": float(ws.cell(24, 2).value or 0.0),
        "odds_2": float(ws.cell(24, 3).value or 0.0),
    }

def _process_file(
    filepath: str,
    tour_name: str,
    gender: str,
    elo_data: str,
    engine: BacktestEngine
) -> None:
    try:
        wb = openpyxl.load_workbook(filepath, data_only=True)
        data = _extract_match_data(wb.active)
        if not data:
            return

        elo_1_str, elo_2_str = EloMatcher.find_elo_ratings(elo_data, data["p1"], data["p2"], "Hard")
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
            gender=gender
        )
    except Exception:
        pass

def _process_tournament(
    tour_dir: str,
    atp_elo: str,
    wta_elo: str,
    engine: BacktestEngine
) -> int:
    tour_name = os.path.basename(tour_dir).replace("_", " ")
    gender = "wta" if "wta" in tour_name.lower() else "atp"
    elo_data = wta_elo if gender == "wta" else atp_elo
    xlsx_files = glob.glob(os.path.join(tour_dir, "*.xlsx"))

    print(f"\nProcessing {tour_name}: {len(xlsx_files)} match files")
    for filepath in xlsx_files:
        _process_file(filepath, tour_name, gender, elo_data, engine)
    return len(xlsx_files)

async def consolidate_january():
    base_dir = "Matchs/2023/January"
    tour_folders = [f for f in glob.glob(os.path.join(base_dir, "*")) if os.path.isdir(f)]
    
    odds_provider = HistoricalOddsProvider()
    evaluator = StrategyEvaluator()
    engine = BacktestEngine(historical_odds=odds_provider, evaluator=evaluator, output_dir="backtest/results")

    atp_elo, wta_elo = await asyncio.gather(ELO_table("ATP"), ELO_table("WTA"))
    print(f"Consolidating backtest results from {len(tour_folders)} tournaments...")

    total_files = sum(_process_tournament(td, atp_elo, wta_elo, engine) for td in tour_folders)

    summary = engine.evaluator.get_summary()
    saved_path = engine.export_summary("january_2023_consolidated_backtest.xlsx")

    print("\n" + "=" * 60)
    print("🏆 BILAN CONSOLIDÉ - JANVIER 2023 (TOUS TOURNOIS)")
    print(f"Total Fichiers Analysés : {total_files}")
    print(f"Total Matchs Matchés   : {len(engine.results)}")
    print(f"Total Paris Déclenchés  : {summary['total_bets']}")
    print(f"Paris Gagnés / Perdus   : {summary['wins']} / {summary['losses']}")
    print(f"Taux de Réussite        : {summary['win_rate']}%")
    print(f"P&L Total               : {summary['total_pnl']} unités")
    print(f"ROI                     : {summary['roi_percent']}%")
    print(f"Rapport consolidé dans  : {saved_path}")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    asyncio.run(consolidate_january())
