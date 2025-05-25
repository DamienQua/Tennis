from datetime import datetime

class DateHelper:
    @staticmethod
    def calculate_matches_last_month(show_class, today, one_month=2629800):
        nb_match_last_month = 0
        date_i = 1

        for i in range(2, len(show_class)):
            if DateHelper.is_valid_date(show_class, i, today, date_i, one_month):
                nb_match_last_month += 1
            else:
                date_i = DateHelper.update_date_index(show_class, i, date_i, nb_match_last_month)
                if not DateHelper.is_within_last_month(show_class, date_i, today, one_month):
                    break

        return nb_match_last_month

    @staticmethod
    def is_valid_date(show_class, i, today, date_i, one_month):
        return show_class[i].text != "Date" and today - datetime.strptime(show_class[date_i].text, "%b %d %Y").timestamp() <= one_month

    @staticmethod
    def is_within_last_month(show_class, date_i, today, one_month):
        return today - datetime.strptime(show_class[date_i].text, "%b %d %Y").timestamp() <= one_month

    @staticmethod
    def update_date_index(show_class, i, date_i, nb_match_last_month):
        date_i = DateHelper.adjust_date_index(show_class, i, date_i, nb_match_last_month)
        return DateHelper.find_valid_date_index(show_class, date_i)

    @staticmethod
    def adjust_date_index(show_class, i, date_i, nb_match_last_month):
        if nb_match_last_month != 0:
            return date_i + nb_match_last_month + 1
        return i + 1 if show_class[date_i].text == "Date" else date_i

    @staticmethod
    def find_valid_date_index(show_class, date_i):
        while True:
            try:
                datetime.strptime(show_class[date_i].text, "%b %d %Y")
                return date_i
            except ValueError:
                date_i -= 1