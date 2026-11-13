"""Persistance sur disque des matchs analysés."""

from typing import Set


class MatchRepository:
    """Gère le stockage des matchs déjà traités et du rapport quotidien."""

    def __init__(
        self,
        reviewed_file: str = "Reviewed_Matchs.txt",
        daily_matches_file: str = "Matchs.txt",
    ) -> None:
        self.reviewed_file = reviewed_file
        self.daily_matches_file = daily_matches_file

    def load_reviewed_urls(self) -> Set[str]:
        """Charge l'ensemble exact des URLs déjà analysées."""
        try:
            with open(self.reviewed_file, "r", encoding="utf-8") as file_handle:
                urls = set()
                for line in file_handle:
                    parts = [p.strip() for p in line.split(",") if p.strip()]
                    if parts and parts[-1].startswith("http"):
                        urls.add(parts[-1])
                return urls
        except OSError:
            return set()

    def save_processed_match(self, match_summary: str, all_matches_text: str) -> None:
        """Ajoute le match à l'historique et met à jour le fichier du jour."""
        with open(self.reviewed_file, "a", encoding="utf-8") as f_reviewed:
            f_reviewed.write(match_summary + "\n")
        with open(self.daily_matches_file, "w", encoding="utf-8") as f_daily:
            f_daily.write(all_matches_text)