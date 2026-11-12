"""
Processes head-to-head (H2H) tennis match data and calculates statistical insights.

This module provides functionality to extract and analyze historical match data between two players,
including win percentages, surface performance, and other relevant statistics.

Key components:
- MatchContext: Stores contextual information about a specific match
- H2HDataProcessor: Processes and calculates head-to-head match statistics
- h2h_table: Async function to generate H2H match insights and update confidence indices

The class handles parsing match details, calculating win percentages across different categories
(all-time, last year, surface-specific, and game-related), and supporting confidence index
generation.
"""

import re
from analysis.indice_confiance import indice_confiance
from analysis.h2h_stats import H2HStats, DateUtils

class MatchContext:
    """Carries contextual HTTP and match metadata for head-to-head processing."""

    def __init__(self, surface, admin_url, header, match_id):
        self.surface = surface
        self.admin_url = admin_url
        self.header = header
        self.match_id = match_id

class H2HDataProcessor:
    """Parses raw HTML head-to-head match rows and updates match stats accordingly."""

    def __init__(self, data, match_vs):
        self.data = data
        self.match_vs = match_vs
        self.stats = H2HStats(match_vs[2], match_vs[3])
        self.go = ""
        self.flag = 0

    def process_h2h_data(self):
        """Processes total matches, individual encounters, and win percentages."""
        self._process_h2h_count()
        self._process_h2h_matches()
        self._calculate_percentages()

    def _process_h2h_count(self):
        if not self.data or not getattr(self.data, "text", None) or "series " not in self.data.text:
            self.match_vs[6:14] = [0] * 8
            return

        ind = 1 if "tied" in self.data.text else 0

        for idx in range(2):
            try:
                split_series = self.data.text.strip().split("series ")[1]
                val = split_series.split(" ")[ind].split("-")[idx].split("\n")[0]
                self.stats.h2h_nb += int(val)
            except (IndexError, ValueError):
                pass

        if self.stats.h2h_nb == 0:
            self.match_vs[6:14] = [0] * 8

    @staticmethod
    def _extract_match_details(row_elem):
        """Extract details from a match row."""
        date_ms = DateUtils.parse_date(row_elem.text.strip().split("\t")[0].strip())
        surface_m = row_elem.text.strip().split("\n")[5].strip().split(",")[0]
        raw_winner = row_elem.text.strip().split("\n")[7].strip()
        winner = re.sub(r"[\(\[].*?[\)\]]", "", raw_winner).split("  d")[0].strip()
        try:
            raw_score = row_elem.text.strip().split("\n")[9].strip()
            score = (
                re.sub(r"[\(\[].*?[\)\]]", "", raw_score)
                .replace("ret.", " ")
                .replace("w/o", "")
                .strip()
            )
        except (IndexError, AttributeError):
            score = "0-0 0-0"
        return date_ms, surface_m, winner, score

    def _update_go_flag(self, row_elem, surface_m, winner):
        """Update the 'go' and 'flag' attributes if conditions are met."""
        if self.go == "" and surface_m in row_elem.text:
            self.go = row_elem.find_all("a")[-1]["href"]
            self.flag = 0 if winner == self.match_vs[2] else 1

    def _process_h2h_matches(self):
        """Process head-to-head matches."""
        h2h_elem = self.data.find(class_="h2h-matches") if self.data else None
        if not h2h_elem:
            return
        h2h_tr = h2h_elem.find_all("tr")[1:]
        surface = self.match_vs[1]
        for row_elem in h2h_tr:
            date_ms, surface_m, winner, score = self._extract_match_details(row_elem)
            self.stats.update_stats(winner, date_ms, surface_m, score, surface)
            self._update_go_flag(row_elem, surface_m, winner)

    def _calculate_percentages(self):
        percentages = self.stats.calculate_percentages()
        self.match_vs[6:14] = (
            percentages["all_time"] + percentages["last_year"] +
            percentages["surface"] + percentages["games"]
        )

async def h2h_table(data, match_vs, session, match_context: MatchContext, indice_tab=None):
    """Extracts H2H records from HTML and updates confidence index array."""
    if indice_tab is None:
        from utils.variables import indice_tab as default_tab
        indice_tab = default_tab

    processor = H2HDataProcessor(data, match_vs)
    processor.process_h2h_data()

    if processor.stats.win_a_sur > 0:
        indice_tab[4] = 2*indice_tab[1]
    if processor.stats.win_b_sur > 0:
        indice_tab[5] = 2*indice_tab[3]

    if processor.go != "":
        await indice_confiance(
            session, match_context.admin_url, "", match_context.match_id,
            match_context.surface, processor.flag, "Tactique", processor.go,
            indice_tab=indice_tab
        )

    return match_vs
