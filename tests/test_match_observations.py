"""Regression checks for the observed TennisInsight activity/statistics markup."""

from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from bs4 import BeautifulSoup

from analysis.match_statistics_processor import MatchStatisticsProcessor
from analysis.tennis_data_parser import StatisticsProcessor, TennisDataParser
from utils.helpers import DateHelper


def statistics(duration="98 minutes", left=("73% (52/71)", "83% (43/52)", "100% (2/2)"),
               right=("66% (41/62)", "76% (31/41)", "67% (2/3)")):
    cells = [""] * 21
    cells[0], cells[2] = "Alexander Zverev", "Arthur Fils"
    for index, first, second in zip((9, 12, 18), left, right):
        cells[index], cells[index + 2] = first, second
    return BeautifulSoup(
        f"<h5>{duration}</h5>" + "".join(f'<div class="col-xs-4">{value}</div>' for value in cells), "lxml"
    )


def activity(ids=("101", "102")):
    rows = "".join(
        f'<tr><th class="activity-clickthroughs no-link">\n'
        f'<a href="https://tennisinsight.com/match/{mid}/2026-turin-atp-wtf/rr/match">Match</a>'
        f'<a data-action="showMatchStats" data-matchid="{mid}"></a></th></tr>' for mid in ids
    )
    return BeautifulSoup(f'<table id="activity-table">{rows}</table><p>Older Qualifying</p>', "lxml")


class TestStatisticObservations(unittest.TestCase):
    def test_missing_semifinal_observations_are_not_zero(self):
        parsed = TennisDataParser.parse_match_statistics(
            statistics("minutes", ("0%(/0)", "0% (/)", "0% (/)")), "Alexander Zverev"
        )
        self.assertEqual(parsed, (None, None, None, None))

    def test_observed_zero_is_distinct_from_no_break_opportunities(self):
        parsed = TennisDataParser.parse_match_statistics(
            statistics(left=("0% (0/20)", "0% (0/2)", "0% (0/0)")), "Alexander Zverev"
        )
        self.assertEqual(parsed, (98, 0.0, 0.0, None))

    def test_target_player_can_be_in_right_column(self):
        self.assertEqual(
            TennisDataParser.parse_match_statistics(statistics(), "Arthur Fils"), (98, 66.0, 76.0, 67.0)
        )

    def test_unknown_player_does_not_inherit_opponent_statistics(self):
        self.assertEqual(
            TennisDataParser.parse_match_statistics(statistics(), "Carlos Alcaraz"), (98, None, None, None)
        )

    def test_missing_duration_does_not_discard_known_service(self):
        self.assertEqual(
            TennisDataParser.parse_match_statistics(statistics("minutes"), "Alexander Zverev"),
            (None, 73.0, 83.0, 100.0),
        )

    def test_missing_response_is_unavailable(self):
        self.assertEqual(TennisDataParser.parse_match_statistics(None), (None, None, None, None))


class TestTournamentObservations(unittest.IsolatedAsyncioTestCase):
    async def aggregate(self, snapshots):
        fetcher = SimpleNamespace(fetch_match_statistics=AsyncMock(side_effect=snapshots))
        processor = MatchStatisticsProcessor(fetcher, StatisticsProcessor())
        return await processor.process_match_statistics(
            "12556", "260684301", "Turin ATP WTF", activity_data=activity(), player_name="Alexander Zverev"
        )

    async def test_missing_latest_match_does_not_make_partial_duration_look_complete(self):
        result = await self.aggregate([
            statistics("minutes", ("0%(/0)", "0%(/)", "0%(/)")), statistics()
        ])
        self.assertEqual(result, (None, None, None, None))

    async def test_missing_older_duration_keeps_latest_service(self):
        self.assertEqual(await self.aggregate([statistics(), statistics("minutes")]), (None, 73.0, 83.0, 100.0))

    async def test_complete_total_and_latest_service_ignore_older_qualifying_label(self):
        self.assertEqual(await self.aggregate([statistics(), statistics("87 minutes")]), (185, 73.0, 83.0, 100.0))

    async def test_empty_response_is_not_zero_playing_time(self):
        fetcher = SimpleNamespace(fetch_player_activity=AsyncMock(return_value=BeautifulSoup("", "lxml")))
        processor = MatchStatisticsProcessor(fetcher, StatisticsProcessor())
        self.assertEqual(await processor.process_match_statistics("12556", "260684301", "Turin"),
                         (None, None, None, None))


class TestRecentActivityCount(unittest.TestCase):
    def test_date_headers_and_tournament_dates_are_not_matches(self):
        labels = ["Date", "Nov 15 2026", " SF", " RR", " RR", " RR",
                  "Date", "Nov 2 2026", " R32", "Date", "Oct 26 2026", " SF", " QF", " R16", " R32",
                  "Date", "Oct 7 2026", " SF", " QF"]
        now = datetime(2026, 11, 21, 23).timestamp()
        self.assertEqual(DateHelper.calculate_matches_last_month([SimpleNamespace(text=x) for x in labels], now), 9)

    def test_future_tournament_and_undated_rows_are_not_played_matches(self):
        labels = ["SF", "Date", "Nov 30 2026", "R32", "Date", "Nov 15 2026", "SF", "RR"]
        now = datetime(2026, 11, 21).timestamp()
        self.assertEqual(DateHelper.calculate_matches_last_month([SimpleNamespace(text=x) for x in labels], now), 2)


if __name__ == "__main__":
    unittest.main()
