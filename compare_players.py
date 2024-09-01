from math import ceil, floor

class AttributeComparator:
    def __init__(self, data):
        self.data = data

    def compare(self, k):
        method_name = f'compare_attribute_{k}'
        if hasattr(self, method_name):
            return getattr(self, method_name)()
        elif k in (6, 14, 20, 21):
            return self.compare_medium_attribute(k)
        elif k in (10, 12, 15, 16, 17, 18, 22, 23, 24):
            return self.compare_regular_attribute(k)
        return 0, 0

    def compare_attribute_4(self):
        diff = float(self.data[5]) - float(self.data[4])
        return (5 * floor((diff - 1) / 10), 0) if diff > 0 else (0, 5 * floor((-diff - 1) / 10))

    def compare_attribute_8(self):
        diff = float(self.data[8]) - float(self.data[9])
        return (3 * ceil(diff / 10), 0) if diff > 0 else (0, 3 * ceil(-diff / 10))

    def compare_attribute_19(self):
        diff = float(self.data[19]) - float(self.data[30])
        return (30, 0) if diff > 0 else (30, 30) if diff == 0 else (0, 30)

    def compare_medium_attribute(self, k):
        diff = float(self.data[k]) - float(self.data[k + (1 if k == 6 else 11)])
        if diff > 0:
            return (ceil(diff / 10), 0) if k == 6 else (10, 0) if k == 14 else (0, 10)
        elif diff < 0:
            return (0, ceil(-diff / 10)) if k == 6 else (0, 10) if k == 14 else (10, 0)
        return (10, 10)

    def compare_regular_attribute(self, k):
        diff = float(self.data[k]) - float(self.data[k + (1 if k in (10, 12) else 11)])
        if k in (10, 12):
            return (5 * ceil(diff / 10), 0) if diff > 0 else (0, 5 * ceil(-diff / 10))
        return (20, 0) if diff > 0 else (20, 20) if diff == 0 else (0, 20)

class Match:
    def __init__(self, match_vs):
        self.data = match_vs
        self.comp = [0, 0, 0]
        self.attribute_comparator = AttributeComparator(self.data)

    def compare_players(self):
        self.compare_attributes()
        self.calculate_odds()
        return self.data

    def compare_attributes(self):
        for k in [4, 8, 19] + list(range(6, 25)):
            if k not in (4, 8, 19):
                comp_a, comp_b = self.attribute_comparator.compare(k)
                self.comp[0] += comp_a
                self.comp[1] += comp_b

    def calculate_odds(self):
        self.comp[2] = self.comp[0] + self.comp[1]
        trj = 0.9
        if self.comp[0] <= self.comp[1]:
            oddsA = round(trj * self.comp[2] / (self.comp[0] + 1e-3), 2)
            oddsB = round(1 / (1 / trj - 1 / oddsA), 2)
        else:
            oddsB = round(trj * self.comp[2] / (self.comp[1] + 1e-3), 2)
            oddsA = round(1 / (1 / trj - 1 / oddsB), 2)
        self.data[36], self.data[37] = oddsA, oddsB

def compare_players(match_vs):
    return Match(match_vs).compare_players()