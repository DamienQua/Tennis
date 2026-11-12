"""
    A processor for handling and aggregating match statistics for a player.

    This class manages the retrieval and processing of match statistics across tournaments,
    providing methods to fetch player activity, extract match-specific statistics, and
    aggregate key performance metrics.

    Attributes:
        data_fetcher: A service responsible for retrieving player match data
        stats_processor: A service for processing individual match statistics

    Methods:
        process_match_statistics: Asynchronously retrieves and processes match statistics
            for a specific player and tournament
        update_statistics: Updates aggregated statistics from individual match data
        is_match_in_tournament: Checks if a match belongs to a specific tournament
        get_match_statistics: Retrieves detailed statistics for a specific match
"""

import asyncio
import aiohttp

class MatchStatisticsProcessor:
    """Processes historical match activity data and aggregates serve and return statistics."""

    def __init__(self, data_fetcher, stats_processor):
        self.data_fetcher = data_fetcher
        self.stats_processor = stats_processor

    async def process_match_statistics(
            self, player_id, match_id, tour_now, activity_data=None
    ):
        """Aggregates serve and return statistics across tournament matches."""
        if activity_data is not None:
            data = activity_data
        else:
            data = await self.data_fetcher.fetch_player_activity(player_id, match_id, 1)
        matches_list = data.find_all(class_="activity-clickthroughs no-link") if data else []

        min_tour, per_first_serve, points_first_serve, per_save_bp = 0, 0, 0, 0

        for m_i, match in enumerate(matches_list):
            if not self.is_match_in_tournament(match, tour_now):
                break
            new_stats = await self.get_match_statistics(matches_list, m_i)
            stats_tuple = (min_tour, per_first_serve, points_first_serve, per_save_bp)
            min_tour, per_first_serve, points_first_serve, per_save_bp = self.update_statistics(
                new_stats, stats_tuple, m_i, data
            )

        return min_tour, per_first_serve, points_first_serve, per_save_bp

    @staticmethod
    def update_statistics(new_stats, current_stats, m_i, data):
        """Updates cumulative match statistics with newly extracted metrics."""
        min_tour, per_first_serve, points_first_serve, per_save_bp = current_stats
        if new_stats:
            min_tour += new_stats[0]
            if m_i == 0 and data and "Qualifying" not in data.text:
                per_first_serve, points_first_serve, per_save_bp = new_stats[1:]
        return min_tour, per_first_serve, points_first_serve, per_save_bp

    @staticmethod
    def is_match_in_tournament(match, tour_now):
        """Verifies if match belongs to current tournament."""
        if not tour_now or not getattr(match, "contents", None) or len(match.contents) < 2:
            return False
        href = match.contents[1].get("href", "") if hasattr(match.contents[1], "get") else ""
        clean_tour = tour_now.lower().replace(" ", "-")
        first_token = clean_tour.split("-")[0]
        return clean_tour in href or (len(first_token) >= 4 and first_token in href)

    async def get_match_statistics(self, matches_list, m_i, *args, **kwargs):
        """Fetches and processes individual match statistics safely."""
        try:
            return await self.stats_processor.process_match_statistics(
                self.data_fetcher, matches_list, m_i
            )
        except (
            aiohttp.ClientError, asyncio.TimeoutError,
            IndexError, AttributeError, KeyError, TypeError, ValueError
        ):
            return None
