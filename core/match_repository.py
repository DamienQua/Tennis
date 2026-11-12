"""
Module managing match persistence on disk.

Handles reading previously analyzed matches and recording newly analyzed matches
to both the persistent review log and the current run output file.
"""

class MatchRepository:
    """Manages file storage for reviewed and daily processed matches."""

    def __init__(self, reviewed_file="Reviewed_Matchs.txt", daily_matches_file="Matchs.txt"):
        self.reviewed_file = reviewed_file
        self.daily_matches_file = daily_matches_file

    def load_reviewed_matches(self):
        """Read the list of all matches reviewed so far."""
        try:
            with open(self.reviewed_file, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def save_processed_match(self, match_summary, all_matches_text):
        """Append a newly analyzed match to reviewed file and refresh daily file."""
        with open(self.reviewed_file, "a", encoding="utf-8") as f_reviewed:
            f_reviewed.write(match_summary + "\n")
        with open(self.daily_matches_file, "w", encoding="utf-8") as f_daily:
            f_daily.write(all_matches_text)
