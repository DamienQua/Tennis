from datetime import datetime

class DateUtils:
    """Helper utilities for parsing dates and validating time windows in H2H analysis."""

    @staticmethod
    def parse_date(date_str):
        """Parses date string into a timestamp."""
        return datetime.strptime(date_str.strip(), "%b %d %Y").timestamp()

    @staticmethod
    def is_within_last_year(date_ms):
        """Checks if given timestamp occurred within the past year."""
        today = datetime.now().timestamp()
        year_ms = 365.25 * 24 * 3600
        return today - date_ms <= year_ms

class PlayerH2H:
    """Stores head-to-head match and game metrics for an individual player."""
    def __init__(self):
        self.wins_all = 0
        self.wins_year = 0
        self.wins_surface = 0
        self.games = 0

class H2HStats:
    """Tracks and calculates head-to-head win percentages and game totals for two players."""

    def __init__(self, player_a, player_b):
        self.player_a = player_a
        self.player_b = player_b
        self.p_a = PlayerH2H()
        self.p_b = PlayerH2H()
        self.h2h_nb = 0
        self.h2h_y = 0

    @property
    def win_a_all(self):
        """Returns or updates player A all-time wins."""
        return self.p_a.wins_all

    @win_a_all.setter
    def win_a_all(self, val):
        """Sets player A all-time wins."""
        self.p_a.wins_all = val

    @property
    def win_b_all(self):
        """Returns or updates player B all-time wins."""
        return self.p_b.wins_all

    @win_b_all.setter
    def win_b_all(self, val):
        """Sets player B all-time wins."""
        self.p_b.wins_all = val

    @property
    def win_a_y(self):
        """Returns or updates player A past-year wins."""
        return self.p_a.wins_year

    @win_a_y.setter
    def win_a_y(self, val):
        """Sets player A past-year wins."""
        self.p_a.wins_year = val

    @property
    def win_b_y(self):
        """Returns or updates player B past-year wins."""
        return self.p_b.wins_year

    @win_b_y.setter
    def win_b_y(self, val):
        """Sets player B past-year wins."""
        self.p_b.wins_year = val

    @property
    def win_a_sur(self):
        """Returns or updates player A surface-specific wins."""
        return self.p_a.wins_surface

    @win_a_sur.setter
    def win_a_sur(self, val):
        """Sets player A surface-specific wins."""
        self.p_a.wins_surface = val

    @property
    def win_b_sur(self):
        """Returns or updates player B surface-specific wins."""
        return self.p_b.wins_surface

    @win_b_sur.setter
    def win_b_sur(self, val):
        """Sets player B surface-specific wins."""
        self.p_b.wins_surface = val

    @property
    def win_a_g(self):
        """Returns or updates player A games won count."""
        return self.p_a.games

    @win_a_g.setter
    def win_a_g(self, val):
        """Sets player A games won count."""
        self.p_a.games = val

    @property
    def win_b_g(self):
        """Returns or updates player B games won count."""
        return self.p_b.games

    @win_b_g.setter
    def win_b_g(self, val):
        """Sets player B games won count."""
        self.p_b.games = val

    def update_stats(self, winner, date_ms, surface, score, current_surface):
        """Updates head-to-head metrics based on an individual match outcome."""
        if winner in self.player_a:
            self._update_player_a_stats(date_ms, surface, score, current_surface)
        else:
            self._update_player_b_stats(date_ms, surface, score, current_surface)

    def _update_player_a_stats(self, date_ms, surface, score, current_surface):
        self.p_a.wins_all += 1
        if DateUtils.is_within_last_year(date_ms):
            self.p_a.wins_year += 1
            self.h2h_y += 1
        if current_surface in surface:
            self.p_a.wins_surface += 1
        self._update_game_stats(score, 0)

    def _update_player_b_stats(self, date_ms, surface, score, current_surface):
        self.p_b.wins_all += 1
        if DateUtils.is_within_last_year(date_ms):
            self.p_b.wins_year += 1
            self.h2h_y += 1
        if current_surface in surface:
            self.p_b.wins_surface += 1
        self._update_game_stats(score, 1)

    def _update_game_stats(self, score, loser_index):
        for set_score in score.split(" "):
            try:
                self.p_a.games += int(set_score.split("-")[loser_index])
                self.p_b.games += int(set_score.split("-")[1-loser_index])
            except (ValueError, IndexError):
                pass

    def calculate_percentages(self):
        """Calculates win percentages across all time, year, surface, and games."""
        return {
            "all_time": self._calculate_percentage(self.p_a.wins_all, self.p_b.wins_all),
            "last_year": self._calculate_percentage(self.p_a.wins_year, self.p_b.wins_year),
            "surface": self._calculate_percentage(self.p_a.wins_surface, self.p_b.wins_surface),
            "games": self._calculate_percentage(self.p_a.games, self.p_b.games)
        }

    @staticmethod
    def _calculate_percentage(wins_a, wins_b):
        total = wins_a + wins_b
        if total <= 0:
            return (0, 0)
        return (round(100 * wins_a / total, 2), round(100 * wins_b / total, 2))
