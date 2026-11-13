"""Script d'exécution de backtests historiques via crawling TennisInsight."""

import asyncio
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import aiohttp
from backtest.backtest_engine import BacktestEngine, print_backtest_summary
from backtest.tournament_crawler import TournamentCrawler
from core.analyze_match import analyze_match
from core.models import MatchAnalysisData
from data_providers.elo_table import elo_table
from main import login

os.environ.pop("SSLKEYLOGFILE", None)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

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


def _log_single_match(match_data: MatchAnalysisData, backtest_res: Any, start: float) -> None:
    elapsed = round(time.perf_counter() - start, 2)
    c_val = backtest_res.match_data.get("confluence", "N/A") if backtest_res else "SKIP"
    print(
        f"Match: {match_data.player_a.name} vs {match_data.player_b.name} "
        f"| Status: {c_val} | Time: {elapsed}s"
    )


async def _analyze_single_match(
    session: aiohttp.ClientSession,
    match_url: str,
    tour_name: str,
    elo_data: str,
    semaphore: asyncio.Semaphore,
    engine: BacktestEngine,
    year: int,
    gender: str,
) -> Optional[Any]:
    async with semaphore:
        try:
            start = time.perf_counter()
            match_data = await analyze_match(
                session, DEFAULT_HEADERS, match_url, [tour_name], elo_data
            )
            if not match_data:
                return None

            pa, pb = match_data.player_a, match_data.player_b
            backtest_res = engine.process_match_result(
                match_url,
                pa.name,
                pb.name,
                match_data.tournament,
                pa.model_odds,
                pb.model_odds,
                elo_a=pa.elo,
                elo_b=pb.elo,
                surface_a=pa.win_pct_career_surface,
                surface_b=pb.win_pct_career_surface,
                year=year,
                gender=gender,
            )
            _log_single_match(match_data, backtest_res, start)
            return backtest_res
        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            OSError,
            ValueError,
            KeyError,
            IndexError,
            AttributeError,
        ) as err:
            print(f"Error analyzing {match_url}: {err}")
            return None


async def _run_matches_batch(
    session: aiohttp.ClientSession,
    matches: List[str],
    tname: str,
    elo_data: str,
    semaphore: asyncio.Semaphore,
    engine: BacktestEngine,
    year: int = 2023,
    gender: str = "atp",
) -> None:
    tasks = [
        _analyze_single_match(
            session, m_url, tname, elo_data, semaphore, engine, year, gender
        )
        for m_url in matches
    ]
    await asyncio.gather(*tasks)


async def run_tournament_backtest(
    tournament_id: str,
    tournament_name: str,
    year: int = 2023,
    gender: str = "atp",
    max_concurrency: int = 3,
    strategy_mode: str = "alpha_5_plus",
) -> Dict[str, Any]:
    """Exécute le backtest pour un tournoi spécifique."""
    crawler = TournamentCrawler()
    engine = BacktestEngine(output_dir="backtest/results", strategy_mode=strategy_mode)
    semaphore = asyncio.Semaphore(max_concurrency)

    async with aiohttp.ClientSession(headers=DEFAULT_HEADERS) as session:
        elo_data = await elo_table(gender.upper(), session=session)
        await login(session)
        print(f"=== Starting Backtest for: {tournament_name} ({year}) ===")
        matches = await crawler.fetch_tournament_matches(session, tournament_id)
        print(f"Found {len(matches)} matches in tournament.\n")
        await _run_matches_batch(
            session, matches, tournament_name, elo_data, semaphore, engine, year, gender
        )

    summary = engine.evaluator.get_summary()
    report_file = f"{tournament_name.replace(' ', '_').lower()}_{year}_backtest.xlsx"
    saved_path = engine.export_summary(report_file)
    print_backtest_summary(
        summary, len(engine.results), saved_path,
        title=f"BACKTEST SUMMARY: {tournament_name} ({year})",
    )
    return summary


async def _run_january_tournaments(
    session: aiohttp.ClientSession,
    crawler: TournamentCrawler,
    engine: BacktestEngine,
    semaphore: asyncio.Semaphore,
    elos: Tuple[str, str],
) -> None:
    for tid, tname, gender in JANUARY_2023_TOURNAMENTS:
        print(f"\n>>> Début analyse : {tname} ({gender.upper()}) <<<")
        elo_data = elos[0] if gender == "atp" else elos[1]
        matches = await crawler.fetch_tournament_matches(session, tid)
        print(f"Matchs trouvés : {len(matches)}")
        await _run_matches_batch(
            session, matches, tname, elo_data, semaphore, engine, year=2023, gender=gender
        )


async def run_january_2023_backtest(
    max_concurrency: int = 3, strategy_mode: str = "alpha_5_plus"
) -> Dict[str, Any]:
    """Exécute le backtest consolidé sur tous les tournois de janvier 2023."""
    crawler = TournamentCrawler()
    engine = BacktestEngine(output_dir="backtest/results", strategy_mode=strategy_mode)
    semaphore = asyncio.Semaphore(max_concurrency)

    async with aiohttp.ClientSession(headers=DEFAULT_HEADERS) as session:
        elos = await asyncio.gather(
            elo_table("ATP", session=session),
            elo_table("WTA", session=session),
        )
        await login(session)
        print("=" * 60)
        print("LANCEMENT DU BACKTEST CONSOLIDÉ - JANVIER 2023 (ATP & WTA)")
        print(f"Total tournois au programme : {len(JANUARY_2023_TOURNAMENTS)}")
        print("=" * 60 + "\n")
        await _run_january_tournaments(session, crawler, engine, semaphore, elos)

    summary = engine.evaluator.get_summary()
    saved_path = engine.export_summary("january_2023_consolidated_backtest.xlsx")
    print_backtest_summary(
        summary, len(engine.results), saved_path,
        title="BILAN CONSOLIDÉ - JANVIER 2023 (ATP & WTA)",
    )
    return summary


if __name__ == "__main__":
    asyncio.run(run_january_2023_backtest(max_concurrency=3))