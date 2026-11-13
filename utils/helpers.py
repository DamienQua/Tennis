"""Utilitaires de calcul et validation de dates pour le suivi des matchs."""

from datetime import datetime
from typing import Sequence


class DateHelper:
    """Calcule et valide les dates de matchs dans une fenêtre temporelle."""

    @staticmethod
    def calculate_matches_last_month(
        show_class: Sequence, today: float, one_month: int = 2629800
    ) -> int:
        """Compte les matchs joués au cours du dernier mois."""
        nb_match_last_month = 0
        date_i = 1
        for idx in range(2, len(show_class)):
            if DateHelper.is_valid_date(show_class, idx, today, date_i, one_month):
                nb_match_last_month += 1
            else:
                date_i = DateHelper.update_date_index(
                    show_class, idx, date_i, nb_match_last_month
                )
                if not DateHelper.is_within_last_month(
                    show_class, date_i, today, one_month
                ):
                    break
        return nb_match_last_month

    @staticmethod
    def is_valid_date(
        show_class: Sequence, idx: int, today: float, date_i: int, one_month: int
    ) -> bool:
        """Vérifie si l'élément courant correspond à un match dans le dernier mois."""
        if show_class[idx].text == "Date":
            return False
        parsed_ts = datetime.strptime(show_class[date_i].text, "%b %d %Y").timestamp()
        return (today - parsed_ts) <= one_month

    @staticmethod
    def is_within_last_month(
        show_class: Sequence, date_i: int, today: float, one_month: int
    ) -> bool:
        """Vérifie si l'horodatage à date_i est dans la fenêtre d'un mois."""
        parsed_ts = datetime.strptime(show_class[date_i].text, "%b %d %Y").timestamp()
        return (today - parsed_ts) <= one_month

    @staticmethod
    def update_date_index(
        show_class: Sequence, idx: int, date_i: int, nb_match_last_month: int
    ) -> int:
        """Met à jour l'index de date en ignorant les lignes non-dates."""
        adjusted = DateHelper.adjust_date_index(
            show_class, idx, date_i, nb_match_last_month
        )
        return DateHelper.find_valid_date_index(show_class, adjusted)

    @staticmethod
    def adjust_date_index(
        show_class: Sequence, idx: int, date_i: int, nb_match_last_month: int
    ) -> int:
        """Calcule l'index ajusté selon le nombre de matchs déjà comptés."""
        if nb_match_last_month != 0:
            return date_i + nb_match_last_month + 1
        return idx + 1 if show_class[date_i].text == "Date" else date_i

    @staticmethod
    def find_valid_date_index(show_class: Sequence, date_i: int) -> int:
        """Recherche en arrière un index de ligne contenant une date valide."""
        while date_i >= 0:
            try:
                datetime.strptime(show_class[date_i].text, "%b %d %Y")
                return date_i
            except (ValueError, IndexError):
                date_i -= 1
        return 0