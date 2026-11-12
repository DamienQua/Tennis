"""
    A class for analyzing match statistics in tennis.

    Provides methods to calculate serve, return, and tiebreak statistics from match data.
    Supports processing statistics for two players with a flag-based approach to handle
    different perspectives.

    Methods:
        calculate_serve_return_stats: Extracts and calculates serve and return percentages
        calculate_tiebreak_stats: Computes tiebreak point win percentages from match scores
        parse_tiebreak_scores: Identifies and counts tiebreak points from match scores
        is_tiebreak: Determines if a given score represents a tiebreak scenario
        update_tiebreak_counts: Updates tiebreak point counts based on score comparison
"""

import re

class MatchStatisticsAnalyzer:
    """Calculates tactical serve, return, break point, and tiebreak metrics from match stats."""

    @staticmethod
    def calculate_serve_return_stats(stats_match, flag):
        """Calculates serve and return percentage metrics for both players."""
        offset_flag = 2 if flag == 1 else 0
        cols = stats_match.find_all(class_="col-xs-4")

        def _val(offset):
            return float(cols[offset + offset_flag].text.strip().split("%")[0])

        p_first = _val(12)
        p_second = _val(15)
        r_first = _val(24)
        r_second = _val(27)
        p_bp = _val(18)
        r_bp = _val(30)

        if flag == 0:
            return [
                p_first, 100 - p_first, p_second, 100 - p_second,
                r_first, 100 - r_first, r_second, 100 - r_second,
                p_bp, 100 - p_bp, r_bp, 100 - r_bp
            ]
        return [
            100 - p_first, p_first, 100 - p_second, p_second,
            100 - r_first, r_first, 100 - r_second, r_second,
            100 - p_bp, p_bp, 100 - r_bp, r_bp
        ]

    def calculate_tiebreak_stats(self, stats_match, _flag=None):
        """Calculates tiebreak win percentages from match scores."""
        header = stats_match.find_all(class_="col-xs-12")[0].find_all("h4")[0]
        scores = re.sub(r"\([^)]*\)", "", header.text.strip())
        if scores:
            tie_break_j1, tie_break_j2 = self.parse_tiebreak_scores(scores)
            total = tie_break_j1 + tie_break_j2
            if total > 0:
                return 100 * tie_break_j1 / total, 100 * tie_break_j2 / total
        return 0, 0

    def parse_tiebreak_scores(self, scores):
        """Parses tiebreak set scores from match score string."""
        tie_break_j1, tie_break_j2 = 0, 0
        for score in scores.split(" "):
            if self.is_tiebreak(score):
                tie_break_j1, tie_break_j2 = self.update_tiebreak_counts(
                    score, tie_break_j1, tie_break_j2
                )
        return tie_break_j1, tie_break_j2

    @staticmethod
    def is_tiebreak(score):
        """Checks if a set score represents a tiebreak."""
        parts = score.split("-")
        return len(parts) == 2 and int(parts[0]) >= 6 and int(parts[1]) >= 6

    @staticmethod
    def update_tiebreak_counts(score, tie_break_j1, tie_break_j2):
        """Increments tiebreak win counts based on score."""
        parts = score.split("-")
        if int(parts[0]) > int(parts[1]):
            tie_break_j1 += 1
        else:
            tie_break_j2 += 1
        return tie_break_j1, tie_break_j2
