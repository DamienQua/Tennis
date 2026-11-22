"""Script d'exécution de backtests historiques via crawling TennisInsight (ELO historiques)."""

import asyncio
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import aiohttp
import pandas as pd
from backtest.backtest_engine import BacktestEngine, print_backtest_summary
from backtest.point_in_time_stats import PointInTimeStats
from backtest.tournament_crawler import TournamentCrawler
from core.analyze_match import analyze_match
from core.models import MatchAnalysisData
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


def _load_historical_stats(gender: str, data_dir: str = "backtest/data") -> PointInTimeStats:
    """Construit un moteur ELO strictement historique depuis les archives locales."""
    frames = []
    for year in (2022, 2023, 2024, 2025, 2026):
        path = os.path.join(data_dir, f"{gender.lower()}_{year}.xlsx")
        if os.path.exists(path):
            frames.append(pd.read_excel(path))
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return PointInTimeStats(combined)


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
    stats_engine: PointInTimeStats,
    semaphore: asyncio.Semaphore,
    engine: BacktestEngine,
    year: int,
    gender: str,
) -> Optional[Any]:
    async with semaphore:
        try:
            start = time.perf_counter()
            match_data = await analyze_match(
                            session,
                            DEFAULT_HEADERS,
                            match_url,
                            [tour_name],
                            elo_data="",
                            enforce_prematch=False,
                        )
            if not match_data:
                return None

            pa, pb = match_data.player_a, match_data.player_b
            hist = engine.odds_provider.get_match_odds(
                pa.name, pb.name, year, gender, tournament=match_data.tournament
            )
            cutoff_date = (
                pd.to_datetime(hist["date"])
                if (hist and hist.get("date"))
                else pd.Timestamp(f"{year}-01-01")
            )
            elo_a = stats_engine.get_player_elo_before(pa.name, cutoff_date, match_data.surface)
            elo_b = stats_engine.get_player_elo_before(pb.name, cutoff_date, match_data.surface)

            backtest_res = engine.process_match_result(
                match_url,
                pa.name,
                pb.name,
                match_data.tournament,
                pa.model_odds,
                pb.model_odds,
                elo_a=elo_a,
                elo_b=elo_b,
                surface_a=pa.win_pct_career_surface,
                surface_b=pb.win_pct_career_surface,
                year=year,
                gender=gender,
                match_date=hist.get("date") if hist else None,
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
    stats_engine: PointInTimeStats,
    semaphore: asyncio.Semaphore,
    engine: BacktestEngine,
    year: int = 2023,
    gender: str = "atp",
) -> None:
    tasks = [
        _analyze_single_match(
            session, m_url, tname, stats_engine, semaphore, engine, year, gender
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
    """Exécute le backtest pour un tournoi spécifique avec ELO historiques."""
    crawler = TournamentCrawler()
    engine = BacktestEngine(output_dir="backtest/results", strategy_mode=strategy_mode)
    semaphore = asyncio.Semaphore(max_concurrency)
    stats_engine = _load_historical_stats(gender)

    async with aiohttp.ClientSession(headers=DEFAULT_HEADERS) as session:
        await login(session)
        print(f"=== Starting Backtest for: {tournament_name} ({year}) ===")
        matches = await crawler.fetch_tournament_matches(session, tournament_id)
        print(f"Found {len(matches)} matches in tournament.\n")
        await _run_matches_batch(
            session, matches, tournament_name, stats_engine, semaphore, engine, year, gender
        )

    summary = engine.evaluator.get_summary()
    report_file = f"{tournament_name.replace(' ', '_').lower()}_{year}_backtest.xlsx"
    saved_path = engine.export_summary(report_file)
    print_backtest_summary(
        summary,
        len(engine.results),
        saved_path,
        title=f"BACKTEST SUMMARY: {tournament_name} ({year})",
    )
    return summary


async def _run_january_tournaments(
    session: aiohttp.ClientSession,
    crawler: TournamentCrawler,
    engine: BacktestEngine,
    semaphore: asyncio.Semaphore,
    stats_engines: Tuple[PointInTimeStats, PointInTimeStats],
) -> None:
    for tid, tname, gender in JANUARY_2023_TOURNAMENTS:
        print(f"\n>>> Début analyse : {tname} ({gender.upper()}) <<<")
        stats_engine = stats_engines[0] if gender == "atp" else stats_engines[1]
        matches = await crawler.fetch_tournament_matches(session, tid)
        print(f"Matchs trouvés : {len(matches)}")
        await _run_matches_batch(
            session, matches, tname, stats_engine, semaphore, engine, year=2023, gender=gender
        )


async def run_january_2023_backtest(
    max_concurrency: int = 3, strategy_mode: str = "alpha_5_plus"
) -> Dict[str, Any]:
    """Exécute le backtest consolidé sur tous les tournois de janvier 2023 (ELO historiques)."""
    crawler = TournamentCrawler()
    engine = BacktestEngine(output_dir="backtest/results", strategy_mode=strategy_mode)
    semaphore = asyncio.Semaphore(max_concurrency)
    stats_engines = (_load_historical_stats("atp"), _load_historical_stats("wta"))

    async with aiohttp.ClientSession(headers=DEFAULT_HEADERS) as session:
        await login(session)
        print("=" * 60)
        print("LANCEMENT DU BACKTEST CONSOLIDÉ - JANVIER 2023 (ATP & WTA)")
        print(f"Total tournois au programme : {len(JANUARY_2023_TOURNAMENTS)}")
        print("=" * 60 + "\n")
        await _run_january_tournaments(session, crawler, engine, semaphore, stats_engines)

    summary = engine.evaluator.get_summary()
    saved_path = engine.export_summary("january_2023_consolidated_backtest.xlsx")
    print_backtest_summary(
        summary,
        len(engine.results),
        saved_path,
        title="BILAN CONSOLIDÉ - JANVIER 2023 (ATP & WTA)",
    )
    return summary


if __name__ == "__main__":
    asyncio.run(run_january_2023_backtest(max_concurrency=3))
