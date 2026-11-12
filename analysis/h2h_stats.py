from datetime import datetime

class DateUtils:
    @staticmethod
    def parse_date(date_str):
        return datetime.strptime(date_str.strip(), "%b %d %Y").timestamp()

    @staticmethod
    def is_within_last_year(date_ms):
        today = datetime.now().timestamp()
        year_ms = 365.25 * 24 * 3600
        return today - date_ms <= year_ms

class H2HStats:
    def __init__(self, player_a, player_b):
        self.player_a = player_a
        self.player_b = player_b
        self.winA_all = self.winB_all = 0
        self.winA_y = self.winB_y = 0
        self.winA_sur = self.winB_sur = 0
        self.winA_G = self.winB_G = 0
        self.h2h_nb = self.h2h_y = 0

    def update_stats(self, winner, date_ms, surface, score, current_surface):
        if winner in self.player_a:
            self._update_player_a_stats(date_ms, surface, score, current_surface)
        else:
            self._update_player_b_stats(date_ms, surface, score, current_surface)

    def _update_player_a_stats(self, date_ms, surface, score, current_surface):
        self.winA_all += 1
        if DateUtils.is_within_last_year(date_ms):
            self.winA_y += 1
            self.h2h_y += 1
        if current_surface in surface:
            self.winA_sur += 1
        self._update_game_stats(score, 0)

    def _update_player_b_stats(self, date_ms, surface, score, current_surface):
        self.winB_all += 1
        if DateUtils.is_within_last_year(date_ms):
            self.winB_y += 1
            self.h2h_y += 1
        if current_surface in surface:
            self.winB_sur += 1
        self._update_game_stats(score, 1)

    def _update_game_stats(self, score, loser_index):
        for set_score in score.split(" "):
            try:
                self.winA_G += int(set_score.split("-")[loser_index])
                self.winB_G += int(set_score.split("-")[1-loser_index])
            except:
                pass

    def calculate_percentages(self):
        return {
            "all_time": self._calculate_percentage(self.winA_all, self.winB_all),
            "last_year": self._calculate_percentage(self.winA_y, self.winB_y),
            "surface": self._calculate_percentage(self.winA_sur, self.winB_sur),
            "games": self._calculate_percentage(self.winA_G, self.winB_G)
        }

    def _calculate_percentage(self, wins_a, wins_b):
        total = wins_a + wins_b
        return (round(100 * wins_a / total, 2), round(100 * wins_b / total, 2)) if total > 0 else (0, 0)