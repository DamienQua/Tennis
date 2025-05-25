class MatchStatisticsProcessor:
    def __init__(self, data_fetcher, stats_processor):
        self.data_fetcher = data_fetcher
        self.stats_processor = stats_processor

    async def process_match_statistics(self, player_id, match_id, tour_now):
        data = await self.data_fetcher.fetch_player_activity(player_id, match_id, 1)
        pAB_matchs = data.find_all(class_="activity-clickthroughs no-link")

        min_tour, per_first_serve, points_first_serve, per_save_bp = 0, 0, 0, 0

        for m_i, match in enumerate(pAB_matchs):
            if not self.is_match_in_tournament(match, tour_now):
                break
            new_stats = await self.get_match_statistics(data, pAB_matchs, tour_now, m_i)
            min_tour, per_first_serve, points_first_serve, per_save_bp = self.update_statistics(
                new_stats, min_tour, per_first_serve, points_first_serve, per_save_bp, m_i, data
            )

        return min_tour, per_first_serve, points_first_serve, per_save_bp

    def update_statistics(self, new_stats, min_tour, per_first_serve, points_first_serve, per_save_bp, m_i, data):
        if new_stats:
            min_tour += new_stats[0]
            if m_i == 0 and "Qualifying" not in data.text:
                per_first_serve, points_first_serve, per_save_bp = new_stats[1:]
        return min_tour, per_first_serve, points_first_serve, per_save_bp

    def is_match_in_tournament(self, match, tour_now):
        return tour_now.lower().replace(" ", "-") in match.contents[1]["href"]

    async def get_match_statistics(self, data, pAB_matchs, tour_now, m_i):
        try:
            return await self.stats_processor.process_match_statistics(self.data_fetcher, pAB_matchs, tour_now, m_i)
        except:
            return None