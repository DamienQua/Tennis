from math import ceil, floor

class Match:
    def __init__(self, match_vs):
        self.data = match_vs
        self.comp = [0, 0, 0]

    def compare_players(self):
        self.compare_specific_attributes()
        self.compare_general_attributes()
        self.calculate_odds()
        return self.data

    def compare_specific_attributes(self):
        for k in (4, 8, 19):
            self.compare_attribute(k)

    def compare_general_attributes(self):
        for k in range(6, 25):
            if k not in (4, 8, 19):
                self.compare_attribute(k)

    def compare_attribute(self, k):
        if k in (4, 8, 19):
            self.compare_special_attribute(k)
        elif k in (6, 14, 20, 21):
            self.compare_medium_attribute(k)
        elif k in (10, 12, 15, 16, 17, 18, 22, 23, 24):
            self.compare_regular_attribute(k)

    def compare_special_attribute(self, k):
        if k == 4:
            self.compare_attribute_4()
        elif k == 8:
            self.compare_attribute_8()
        else:  # k == 19
            self.compare_attribute_19()

    def compare_medium_attribute(self, k):
        if k == 6:
            self.compare_attribute_6()
        else:
            self.compare_attribute_14_20_21(k)

    def compare_regular_attribute(self, k):
        if k in (10, 12):
            self.compare_attribute_10_12(k)
        else:
            self.compare_attribute_15_to_24(k)

    def compare_attribute_4(self):
        diff = float(self.data[5]) - float(self.data[4])
        if diff > 0:
            self.comp[0] += 5 * floor((diff - 1) / 10)
        elif diff < 0:
            self.comp[1] += 5 * floor((-diff - 1) / 10)

    def compare_attribute_8(self):
        diff = float(self.data[8]) - float(self.data[9])
        if diff > 0:
            self.comp[0] += 3 * ceil(diff / 10)
        elif diff < 0:
            self.comp[1] += 3 * ceil(-diff / 10)

    def compare_attribute_19(self):
        diff = float(self.data[19]) - float(self.data[30])
        if diff > 0:
            self.comp[0] += 30
        elif diff == 0:
            self.comp[0] += 30
            self.comp[1] += 30
        else:
            self.comp[1] += 30

    def compare_attribute_6(self):
        diff = float(self.data[6]) - float(self.data[7])
        if diff > 0:
            self.comp[0] += ceil(diff / 10)
        elif diff < 0:
            self.comp[1] += ceil(-diff / 10)

    def compare_attribute_14_20_21(self, k):
        diff = float(self.data[k]) - float(self.data[k + 11])
        if diff > 0:
            self.comp[0 if k == 14 else 1] += 10
        elif diff == 0:
            self.comp[0] += 10
            self.comp[1] += 10
        else:
            self.comp[1 if k == 14 else 0] += 10

    def compare_attribute_10_12(self, k):
        diff = float(self.data[k]) - float(self.data[k + 1])
        if diff > 0:
            self.comp[0] += 5 * ceil(diff / 10)
        elif diff < 0:
            self.comp[1] += 5 * ceil(-diff / 10)

    def compare_attribute_15_to_24(self, k):
        diff = float(self.data[k]) - float(self.data[k + 11])
        if diff > 0:
            self.comp[0] += 20
        elif diff == 0:
            self.comp[0] += 20
            self.comp[1] += 20
        else:
            self.comp[1] += 20

    def calculate_odds(self):
        self.comp[2] = self.comp[0] + self.comp[1]
        trj = 0.9

        if self.comp[0] <= self.comp[1]:
            oddsA = round(trj * self.comp[2] / (self.comp[0] + 1e-3), 2)
            oddsB = round(1 / (1 / trj - 1 / oddsA), 2)
        else:
            oddsB = round(trj * self.comp[2] / (self.comp[1] + 1e-3), 2)
            oddsA = round(1 / (1 / trj - 1 / oddsB), 2)

        self.data[36] = oddsA
        self.data[37] = oddsB

def compare_players(match_vs):
    match = Match(match_vs)
    return match.compare_players()