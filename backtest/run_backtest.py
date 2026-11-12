"""
Runner script for executing historical tennis backtests.

Connects to TennisInsight, crawls tournament matches, analyzes matches concurrently,
retrieves historical closing odds, simulates betting strategy, and exports Excel reports.
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.pop("SSLKEYLOGFILE", None)
import asyncio
import time
from typing import List, Dict, Any, Optional, Tuple
import aiohttp
from dotenv import dotenv_values
import numpy as np

from backtest.tournament_crawler import TournamentCrawler
from backtest.historical_odds import HistoricalOddsProvider
from backtest.strategy_evaluator import StrategyEvaluator
from backtest.backtest_engine import BacktestEngine
from core.analyze_match import analyze_match
from data_providers.ELO_table import ELO_table

async def login(session: aiohttp.ClientSession) -> None:
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
    tokens = [t.strip() for t in result_str.split(",")]
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

async def _analyze_single_match(
    session: aiohttp.ClientSession,
    header: dict,
    match_url: str,
    tournaments: Any,
    elo_data: str,
    semaphore: asyncio.Semaphore,
    engine: BacktestEngine,
    year: int,
    gender: str
) -> Optional[Any]:
    async with semaphore:
        try:
            start = time.perf_counter()
            match_res = await analyze_match(session, header, match_url, tournaments, elo_data)
            m = parse_match_metrics(match_res)
            
            backtest_res = engine.process_match_result(
                match_url,
                m["p_a"],
                m["p_b"],
                m["tour"],
                m["odds_a"],
                m["odds_b"],
                elo_a=m["elo_a"],
                elo_b=m["elo_b"],
                surface_a=m["surface_a"],
                surface_b=m["surface_b"],
                year=year,
                gender=gender
            )
            elapsed = round(time.perf_counter() - start, 2)
            confluence = backtest_res.match_data.get("confluence", "N/A") if backtest_res else "SKIP"
            print(f"Match: {m['p_a']} vs {m['p_b']} | Status: {confluence} | Time: {elapsed}s")
            return backtest_res
        except Exception as e:
            print(f"Error analyzing {match_url}: {e}")
            return None

async def run_tournament_backtest(
    tournament_id: str,
    tournament_name: str,
    year: int = 2023,
    gender: str = "atp",
    max_concurrency: int = 3
) -> Dict[str, Any]:
    header = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1)"}
    crawler = TournamentCrawler()
    engine = BacktestEngine(output_dir="backtest/results")
    semaphore = asyncio.Semaphore(max_concurrency)

    elo_data = await ELO_table(gender.upper())

    async with aiohttp.ClientSession(headers=header) as session:
        await login(session)
        print(f"=== Starting Backtest for: {tournament_name} ({year}) ===")
        matches = await crawler.fetch_tournament_matches(session, tournament_id)
        print(f"Found {len(matches)} matches in tournament.\n")

        tasks = [
            _analyze_single_match(
                session, header, m_url, np.array([tournament_name]), elo_data, semaphore, engine, year, gender
            )
            for m_url in matches
        ]
        await asyncio.gather(*tasks)

    summary = engine.evaluator.get_summary()
    report_file = f"{tournament_name.replace(' ', '_').lower()}_{year}_backtest.xlsx"
    saved_path = engine.export_summary(report_file)

    print("\n" + "=" * 55)
    print(f"BACKTEST SUMMARY: {tournament_name} ({year})")
    print(f"Total Matches Analyzed: {len(engine.results)}")
    print(f"Total Bets Placed:      {summary['total_bets']}")
    print(f"Wins / Losses:          {summary['wins']} / {summary['losses']}")
    print(f"Win Rate:               {summary['win_rate']}%")
    print(f"Total P&L:              {summary['total_pnl']} units")
    print(f"ROI:                    {summary['roi_percent']}%")
    print(f"Report exported to:     {saved_path}")
    print("=" * 55 + "\n")

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

async def run_january_2023_backtest(max_concurrency: int = 3) -> Dict[str, Any]:
    header = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1)"}
    crawler = TournamentCrawler()
    engine = BacktestEngine(output_dir="backtest/results")
    semaphore = asyncio.Semaphore(max_concurrency)

    atp_elo, wta_elo = await asyncio.gather(ELO_table("ATP"), ELO_table("WTA"))

    async with aiohttp.ClientSession(headers=header) as session:
        await login(session)
        print("=" * 60)
        print("🚀 LANCEMENT DU BACKTEST CONSOLIDÉ - JANVIER 2023 (ATP & WTA)")
        print(f"Total tournois au programme : {len(JANUARY_2023_TOURNAMENTS)}")
        print("=" * 60 + "\n")

        for tid, tname, gender in JANUARY_2023_TOURNAMENTS:
            print(f"\n>>> Début analyse : {tname} ({gender.upper()}) <<<")
            elo_data = atp_elo if gender == "atp" else wta_elo
            matches = await crawler.fetch_tournament_matches(session, tid)
            print(f"Matchs trouvés : {len(matches)}")

            tasks = [
                _analyze_single_match(
                    session, header, m_url, np.array([tname]), elo_data, semaphore, engine, 2023, gender
                )
                for m_url in matches
            ]
            await asyncio.gather(*tasks)

    summary = engine.evaluator.get_summary()
    report_file = "january_2023_consolidated_backtest.xlsx"
    saved_path = engine.export_summary(report_file)

    print("\n" + "=" * 60)
    print("🏆 BILAN CONSOLIDÉ - JANVIER 2023 (ATP & WTA)")
    print(f"Total Matchs Analysés : {len(engine.results)}")
    print(f"Total Paris Confluence  : {summary['total_bets']}")
    print(f"Gagnés / Perdus         : {summary['wins']} / {summary['losses']}")
    print(f"Taux de Réussite        : {summary['win_rate']}%")
    print(f"P&L Total               : {summary['total_pnl']} unités")
    print(f"ROI                     : {summary['roi_percent']}%")
    print(f"Rapport consolidé dans  : {saved_path}")
    print("=" * 60 + "\n")

    return summary

if __name__ == "__main__":
    asyncio.run(run_january_2023_backtest(max_concurrency=3))
