"""
Compares two players' attributes and calculates match odds.

This module provides functionality to compare player attributes and determine
match probabilities through the following key components:
- AttributeComparator: Calculates differences between player attributes
- Match: Processes player comparisons and generates match odds
- compare_players(): Main entry point for comparing two players

The comparison involves analyzing various numerical attributes, applying
weighted comparisons, and computing final match odds with a trajectory factor.

Args:
    match_vs (list): A list containing player attributes and match-related data

Returns:
    list: Updated match data with calculated odds
"""

from math import ceil, floor

def _safe_float(val, default=0.0):
    try:
        str_val = str(val).strip()
        return float(str_val) if str_val else default
    except (ValueError, TypeError):
        return default

class AttributeComparator:
    """Compares individual player attributes and yields comparative score tuples."""

    def __init__(self, data):
        self.data = data

    def compare(self, attr_idx):
        """Dispatches attribute comparison for index attr_idx to specific handlers."""
        method_name = f'compare_attribute_{attr_idx}'
        if hasattr(self, method_name):
            return getattr(self, method_name)()
        if attr_idx in (6, 14, 20, 21):
            return self.compare_medium_attribute(attr_idx)
        if attr_idx in (10, 12, 15, 16, 17, 18, 22, 23, 24):
            return self.compare_regular_attribute(attr_idx)
        return 0, 0

    def compare_attribute_4(self):
        """Compares player rankings (index 4)."""
        diff = float(self.data[5]) - float(self.data[4])
        return (5 * floor((diff - 1) / 10), 0) if diff > 0 else (0, 5 * floor((-diff - 1) / 10))

    def compare_attribute_8(self):
        """Compares player Elo ratings (index 8)."""
        diff = float(self.data[8]) - float(self.data[9])
        return (3 * ceil(diff / 10), 0) if diff > 0 else (0, 3 * ceil(-diff / 10))

    def compare_attribute_19(self):
        """Compares return points won (index 19)."""
        diff = float(self.data[19]) - float(self.data[30])
        return (30, 0) if diff > 0 else (30, 30) if diff == 0 else (0, 30)

    def compare_medium_attribute(self, attr_idx):
        """Compares medium-weighted player attributes."""
        offset = 1 if attr_idx == 6 else 11
        diff = float(self.data[attr_idx]) - float(self.data[attr_idx + offset])
        if diff == 0:
            return (10, 10)
        if attr_idx == 6:
            return (ceil(diff / 10), 0) if diff > 0 else (0, ceil(-diff / 10))
        if attr_idx == 14:
            return (10, 0) if diff > 0 else (0, 10)
        return (0, 10) if diff > 0 else (10, 0)

    def compare_regular_attribute(self, attr_idx):
        """Compares standard player attributes."""
        offset = 1 if attr_idx in (10, 12) else 11
        diff = float(self.data[attr_idx]) - float(self.data[attr_idx + offset])
        if attr_idx in (10, 12):
            return (5 * ceil(diff / 10), 0) if diff > 0 else (0, 5 * ceil(-diff / 10))
        if diff == 0:
            return (20, 20)
        return (20, 0) if diff > 0 else (0, 20)

class Match:
    """Manages player attribute comparison and model odds calculation for a match."""

    def __init__(self, match_vs):
        self.data = match_vs
        self.comp = [0, 0, 0]
        self.attribute_comparator = AttributeComparator(self.data)

    def compare_players(self):
        """Coordinates full player attribute comparison and model odds calculation."""
        self.compare_attributes()
        self.add_odds_spread()
        self.calculate_odds()
        return self.data

    def compare_attributes(self):
            # Attributes to compare: 4 (ranking), 8 (H2H 1y), 19 (career surface %),
        """Iterates through all comparative player attributes."""
        # and attributes in range(6, 25)
        attributes_to_compare = [4] + list(range(6, 25))
        for attr_idx in attributes_to_compare:
            comp_a, comp_b = self.attribute_comparator.compare(attr_idx)
            self.comp[0] += comp_a
            self.comp[1] += comp_b

    def add_odds_spread(self):
        """Adjusts model comparison scores using odds spread."""
        self.comp[0] += _safe_float(self.data[42]) * 5
        self.comp[1] += _safe_float(self.data[43]) * 5
        self.comp[2] = self.comp[0] + self.comp[1]

    def calculate_odds(self):
        """Calculates model odds for players A and B based on comparison scores."""
        trj = 0.9
        if self.comp[0] <= self.comp[1]:
            odds_a = round(trj * self.comp[2] / (self.comp[0] + 1e-3), 2)
            odds_b = round(1 / (1 / trj - 1 / odds_a), 2)
        else:
            odds_b = round(trj * self.comp[2] / (self.comp[1] + 1e-3), 2)
            odds_a = round(1 / (1 / trj - 1 / odds_b), 2)
        self.data[36], self.data[37] = odds_a, odds_b

def compare_players(match_vs):
    """Coordinates comparison of player attributes and odds calculation."""
    return Match(match_vs).compare_players()
