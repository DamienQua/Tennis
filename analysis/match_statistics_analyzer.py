"""
    A class for analyzing match statistics in tennis.
    
    Provides methods to calculate serve, return, and tiebreak statistics from match data.
    Supports processing statistics for two players with a flag-based approach to handle different perspectives.
    
    Methods:
        calculate_serve_return_stats: Extracts and calculates serve and return performance percentages
        calculate_tiebreak_stats: Computes tiebreak point win percentages from match scores
        parse_tiebreak_scores: Identifies and counts tiebreak points from match scores
        is_tiebreak: Determines if a given score represents a tiebreak scenario
        update_tiebreak_counts: Updates tiebreak point counts based on score comparison
"""

import re

class MatchStatisticsAnalyzer:
    def calculate_serve_return_stats(self, stats_match, flag):
        j2 = 2 if flag == 1 else 0
        points_first_serve = float(stats_match.find_all(class_="col-xs-4")[12+j2].text.strip().split("%")[0])
        points_second_serve = float(stats_match.find_all(class_="col-xs-4")[15+j2].text.strip().split("%")[0])
        return_first_serve = float(stats_match.find_all(class_="col-xs-4")[24+j2].text.strip().split("%")[0])
        return_second_serve = float(stats_match.find_all(class_="col-xs-4")[27+j2].text.strip().split("%")[0])
        points_save_bp = float(stats_match.find_all(class_="col-xs-4")[18+j2].text.strip().split("%")[0])
        return_save_bp = float(stats_match.find_all(class_="col-xs-4")[30+j2].text.strip().split("%")[0])
        
        if flag == 0:
            return [points_first_serve, 100-points_first_serve, points_second_serve, 100-points_second_serve,
                    return_first_serve, 100-return_first_serve, return_second_serve, 100-return_second_serve,
                    points_save_bp, 100-points_save_bp, return_save_bp, 100-return_save_bp]
        else:
            return [100-points_first_serve, points_first_serve, 100-points_second_serve, points_second_serve,
                    100-return_first_serve, return_first_serve, 100-return_second_serve, return_second_serve,
                    100-points_save_bp, points_save_bp, 100-return_save_bp, return_save_bp]

    def calculate_tiebreak_stats(self, stats_match, flag):
        scores = re.sub(r"\([^)]*\)", "", stats_match.find_all(class_="col-xs-12")[0].find_all("h4")[0].text.strip())
        if scores:
            tie_break_j1, tie_break_j2 = self.parse_tiebreak_scores(scores)
            total = tie_break_j1 + tie_break_j2
            if total > 0:
                return 100 * tie_break_j1 / total, 100 * tie_break_j2 / total
        return 0, 0

    def parse_tiebreak_scores(self, scores):
        tie_break_j1, tie_break_j2 = 0, 0
        for score in scores.split(" "):
            if self.is_tiebreak(score):
                tie_break_j1, tie_break_j2 = self.update_tiebreak_counts(score, tie_break_j1, tie_break_j2)
        return tie_break_j1, tie_break_j2

    def is_tiebreak(self, score):
        s = score.split("-")
        return len(s) == 2 and int(s[0]) >= 6 and int(s[1]) >= 6

    def update_tiebreak_counts(self, score, tie_break_j1, tie_break_j2):
        s = score.split("-")
        if int(s[0]) > int(s[1]):
            tie_break_j1 += 1
        else:
            tie_break_j2 += 1
        return tie_break_j1, tie_break_j2