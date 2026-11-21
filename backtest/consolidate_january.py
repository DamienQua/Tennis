"""Recompute January 2023 from local archives and strictly prior results.

Legacy match workbooks contain undated features and cannot establish what was
known before a match. This entry point now delegates to the historical runner.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtest.run_backtest import run_january_2023_backtest


async def consolidate_january(
    strategy_mode: str = "alpha_5_plus", *,
    data_dir: str = "backtest/data", output_dir: str = "backtest/results",
) -> Dict[str, Any]:
    """Export one consolidated report without scraping current statistics/ELO."""
    return await run_january_2023_backtest(
        strategy_mode=strategy_mode, data_dir=data_dir, output_dir=output_dir,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Consolidate January 2023 from local archives")
    parser.add_argument("--data-dir", default="backtest/data")
    parser.add_argument("--output-dir", default="backtest/results")
    args = parser.parse_args()
    print(asyncio.run(consolidate_january(data_dir=args.data_dir, output_dir=args.output_dir)))
