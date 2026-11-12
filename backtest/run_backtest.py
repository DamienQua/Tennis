"""
Runner script for executing historical tennis backtests.

Connects to TennisInsight, crawls tournament matches, analyzes matches concurrently,
retrieves historical closing odds, simulates betting strategy, and exports Excel reports.
"""

import asyncio
import os
import sys
import time
from typing import List, Dict, Any, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import aiohttp
from dotenv import dotenv_values
import numpy as np

from backtest.tournament_crawler import TournamentCrawler
from backtest.historical_odds import HistoricalOddsProvider
from backtest.strategy_evaluator import StrategyEvaluator
from backtest.backtest_engine import BacktestEngine, print_backtest_summary
from core.analyze_match import analyze_match
from data_providers.ELO_table import elo_table

os.environ.pop("SSLKEYLOGFILE", None)

async def login(session: aiohttp.ClientSession) -> None:
    """Logs into TennisInsight with credentials from environment."""
    config = dotenv_values(".env")
    username = config.get("TENNISINSIGHT_LOGIN")
    password = config.get("TENNISINSIGHT_PASSWORD")
    if not username or not password:
        raise ValueError("Missing TENNISINSIGHT credentials in .env")
    payload = {"log": username, "pwd": password}
    await session.post("https://tennisinsight.com/wp-login.php", data=payload)

def _safe_float(val: str) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def parse_match_metrics(result_str: str) -> Dict[str, Any]:
    """Parses model odds, player names, and ratings from match result."""
    tokens = [token.strip() for token in result_str.split(",")]
    padded = (tokens + [""] * 15)[:15]
    return {
        "tour": padded[0],
        "surface": padded[1],
        "p_a": padded[2],
        "p_b": padded[3],
        "odds_a": _safe_float(padded[4]),
        "odds_b": _safe_float(padded[5]),
        "book_a": _safe_float(padded[6]),
        "book_b": _safe_float(padded[7]),
        "elo_a": _safe_float(padded[8]),
        "elo_b": _safe_float(padded[9]),
        "surface_a": _safe_float(padded[13]),
        "surface_b": _safe_float(padded[14])
    }

def _log_single_match(metrics: dict, backtest_res: Any, start: float) -> None:
    """Logs the analyzed match outcome and processing time."""
    elapsed = round(time.perf_counter() - start, 2)
    c_val = backtest_res.match_data.get("confluence", "N/A") if backtest_res else "SKIP"
    print(f"Match: {metrics['p_a']} vs {metrics['p_b']} | Status: {c_val} | Time: {elapsed}s")

async def _analyze_single_match(*args, **kwargs) -> Optional[Any]:
    """Analyzes a single match and evaluates historical confluence strategy."""
    m_url = args[2]
    async with args[5]:
        try:
            start = time.perf_counter()
            match_res = await analyze_match(args[0], args[1], m_url, args[3], args[4])
            metrics = parse_match_metrics(match_res)

            backtest_res = args[6].process_match_result(
                m_url,
                metrics["p_a"],
                metrics["p_b"],
                metrics["tour"],
                metrics["odds_a"],
                metrics["odds_b"],
                elo_a=metrics["elo_a"],
                elo_b=metrics["elo_b"],
                surface_a=metrics["surface_a"],
                surface_b=metrics["surface_b"],
                year=args[7],
                gender=args[8]
            )
            _log_single_match(metrics, backtest_res, start)
            return backtest_res
        except (
            aiohttp.ClientError, asyncio.TimeoutError, OSError,
            ValueError, KeyError, IndexError, AttributeError
        ) as err:
            print(f"Error analyzing {m_url}: {e}")
            return None

async def _run_matches_batch(*args, **kwargs) -> None:
    session = args[0]
    header = args[1]
    matches = args[2]
    tname = args[3]
    elo_data = args[4]
    semaphore = args[5]
    engine = args[6]
    year = kwargs.get("year", 2023)
    gender = kwargs.get("gender", "atp")
    tasks = [
        _analyze_single_match(
            session, header, m_url, np.array([tname]),
            elo_data, semaphore, engine, year, gender
        )
        for m_url in matches
    ]
    await asyncio.gather(*tasks)

async def run_tournament_backtest(
        tournament_id: str,
        tournament_name: str,
        year: int = 2023,
        gender: str = "atp",
        max_concurrency: int = 3
) -> Dict[str, Any]:
    """Runs backtest pipeline for matches within a specific tournament."""
    header = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1)"}
    crawler = TournamentCrawler()
    engine = BacktestEngine(output_dir="backtest/results")
    semaphore = asyncio.Semaphore(max_concurrency)

    elo_data = await elo_table(gender.upper())

    async with aiohttp.ClientSession(headers=header) as session:
        await login(session)
        print(f"=== Starting Backtest for: {tournament_name} ({year}) ===")
        matches = await crawler.fetch_tournament_matches(session, tournament_id)
        print(f"Found {len(matches)} matches in tournament.\n")
        await _run_matches_batch(
            session, header, matches, tournament_name,
            elo_data, semaphore, engine, year=year, gender=gender
        )

    summary = engine.evaluator.get_summary()
    report_file = f"{tournament_name.replace(' ', '_').lower()}_{year}_backtest.xlsx"
    saved_path = engine.export_summary(report_file)
    print_backtest_summary(
        summary, len(engine.results), saved_path,
        title=f"BACKTEST SUMMARY: {tournament_name} ({year})"
    )

    return summary

JANUARY_2023_TOURNAMENTS = [
    ("23793", "2023 Pune ATP 250", "atp"),
    ("23792", "2023 Adelaide 1 ATP 250", "atp"),
    ("23803", "2023 Auckland ATP 250", "atp"),
    ("23806", "2023 Adelaide 2 ATP 250", "atp"),
    ("23814", "2023 Australian Open ATP Slam", "atp"),
    ("23790", "2023 Adelaide 1 WTA 500", "wta"),
    ("23791", "2023 Auckland WTA 250", "wta"),
    ("23804", "2023 Hobart WTA 250", "wta"),
    ("23805", "2023 Adelaide 2 WTA 500", "wta"),
    ("23815", "2023 Australian Open WTA Slam", "wta"),
    ("23831", "2023 Hua Hin WTA 250", "wta"),
    ("23832", "2023 Lyon WTA 250", "wta"),
]

async def _run_january_tournaments(
        session: aiohttp.ClientSession,
        crawler: TournamentCrawler,
        engine: BacktestEngine,
        semaphore: asyncio.Semaphore,
        elos: Tuple[str, str]
) -> None:
    """Iterates through January tournaments and processes batches of matches."""
    hdr = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1)"}
    for tid, tname, gender in JANUARY_2023_TOURNAMENTS:
        print(f"\n>>> Début analyse : {tname} ({gender.upper()}) <<<")
        elo_data = elos[0] if gender == "atp" else elos[1]
        matches = await crawler.fetch_tournament_matches(session, tid)
        print(f"Matchs trouvés : {len(matches)}")
        await _run_matches_batch(
            session, hdr, matches, tname,
            elo_data, semaphore, engine, year=2023, gender=gender
        )

async def run_january_2023_backtest(max_concurrency: int = 3) -> Dict[str, Any]:
    """Runs backtest on all ATP and WTA tournaments in January 2023."""
    header = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1)"}
    crawler = TournamentCrawler()
    engine = BacktestEngine(output_dir="backtest/results")
    semaphore = asyncio.Semaphore(max_concurrency)
    elos = await asyncio.gather(elo_table("ATP"), elo_table("WTA"))

    async with aiohttp.ClientSession(headers=header) as session:
        await login(session)
        print("=" * 60)
        print("🚀 LANCEMENT DU BACKTEST CONSOLIDÉ - JANVIER 2023 (ATP & WTA)")
        print(f"Total tournois au programme : {len(JANUARY_2023_TOURNAMENTS)}")
        print("=" * 60 + "\n")
        await _run_january_tournaments(session, crawler, engine, semaphore, elos)

    summary = engine.evaluator.get_summary()
    saved_path = engine.export_summary("january_2023_consolidated_backtest.xlsx")
    print_backtest_summary(
        summary, len(engine.results), saved_path,
        title="BILAN CONSOLIDÉ - JANVIER 2023 (ATP & WTA)"
    )

    return summary

if __name__ == "__main__":
    asyncio.run(run_january_2023_backtest(max_concurrency=3))
