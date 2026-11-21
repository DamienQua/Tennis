"""Historical runners using local archives and strictly prior match results."""

import argparse
import asyncio
import re
import sys
from pathlib import Path
from typing import Any, Dict

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtest.point_in_time_backtest import PointInTimeBacktester
from backtest.strategy_evaluator import StrategyEvaluator


async def run_tournament_backtest(
    tournament_id: str,
    tournament_name: str,
    year: int = 2023,
    gender: str = "atp",
    max_concurrency: int = 3,
    strategy_mode: str = "alpha_5_plus",
    *, data_dir: str = "backtest/data", output_dir: str = "backtest/results",
) -> Dict[str, Any]:
    """Use the exact Tournament column name; former crawl arguments remain compatible.

    tournament_id and max_concurrency are ignored: no network data is consulted.
    Missing archives or an unknown tournament produce an explicit error.
    """
    runner = PointInTimeBacktester(data_dir=data_dir, output_dir=output_dir, strategy_mode=strategy_mode)
    slug = re.sub(r"[^a-z0-9]+", "_", tournament_name.lower()).strip("_") or "tournament"
    return runner.run_backtest_for_year(
        year, gender, tournament=tournament_name,
        report_name=f"{gender}_{year}_{slug}_{strategy_mode}_backtest.xlsx",
    )


async def run_january_2023_backtest(
    max_concurrency: int = 3, strategy_mode: str = "alpha_5_plus", *,
    data_dir: str = "backtest/data", output_dir: str = "backtest/results",
) -> Dict[str, Any]:
    """Consolidate January ATP/WTA without fetching current stats or ELO."""
    evaluator = StrategyEvaluator()
    records = []
    errors = {}
    for circuit in ("atp", "wta"):
        runner = PointInTimeBacktester(data_dir=data_dir, output_dir=output_dir, strategy_mode=strategy_mode)
        summary = runner.run_backtest_for_year(
            2023, circuit, month=1, report_name=f"january_2023_{circuit}_{strategy_mode}_backtest.xlsx",
        )
        if "error" in summary:
            errors[circuit] = summary["error"]
        evaluator.bets.extend(runner.evaluator.bets)
        records.extend(dict(record, circuit=circuit) for record in runner.records)
    combined = PointInTimeBacktester(
        data_dir=data_dir, output_dir=output_dir, strategy_mode=strategy_mode, evaluator=evaluator,
    )
    combined.records = records
    result = evaluator.get_summary()
    result.update(total_matches=len(records))
    if errors:
        result.update(archive_errors=errors, incomplete=True)
    combined._export_results("january_2023_consolidated_backtest.xlsx", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Local, point-in-time historical backtest")
    parser.add_argument("--year", type=int, default=2023)
    parser.add_argument("--gender", choices=("atp", "wta"), default="atp")
    parser.add_argument("--tournament", help="Exact Tournament name in the local archive")
    parser.add_argument("--data-dir", default="backtest/data")
    parser.add_argument("--output-dir", default="backtest/results")
    parser.add_argument("--january-2023", action="store_true")
    args = parser.parse_args()
    if args.january_2023:
        result = asyncio.run(run_january_2023_backtest(data_dir=args.data_dir, output_dir=args.output_dir))
    else:
        runner = PointInTimeBacktester(data_dir=args.data_dir, output_dir=args.output_dir)
        result = runner.run_backtest_for_year(args.year, args.gender, tournament=args.tournament)
    print(result)


if __name__ == "__main__":
    main()
