"""Utilitaires partagés : parsing, normalisation texte/surface/URL, dates et retries HTTP."""

import asyncio
from datetime import datetime
import re
from typing import Any, Optional, Sequence
import unicodedata
import aiohttp

_EN_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_EN_DATE_RE = re.compile(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})$")
_MATCH_ID_RE = re.compile(r"/match/(\d+)(?:/|$)")
_CHAR_TRANSLATION = str.maketrans({
    "ł": "l",
    "Ł": "l",
    "đ": "d",
    "Đ": "d",
    "ø": "o",
    "Ø": "o",
    "ß": "ss",
})


def safe_float(val: Any, default: float = 0.0) -> float:
    """Convertit une valeur quelconque en float sans lever d'exception."""
    if val is None:
        return default
    try:
        cleaned = str(val).replace(",", ".").strip()
        return float(cleaned) if cleaned else default
    except (ValueError, TypeError, AttributeError):
        return default


def safe_int(val: Any, default: int = 0) -> int:
    """Convertit une valeur quelconque en int sans lever d'exception."""
    if val is None:
        return default
    try:
        cleaned = str(val).replace(",", ".").strip()
        return int(float(cleaned)) if cleaned else default
    except (ValueError, TypeError, AttributeError):
        return default


def normalize_surface(surface: str) -> str:
    """Normalise une surface de tennis en bucket canonique ('hard', 'clay', 'grass')."""
    s_low = (surface or "").strip().lower()
    if "clay" in s_low:
        return "clay"
    if "grass" in s_low:
        return "grass"
    return "hard"


def normalize_text(text: str) -> str:
    """Supprime accents/diacritiques, normalise casse et espaces."""
    translated = (text or "").translate(_CHAR_TRANSLATION)
    decomposed = unicodedata.normalize("NFKD", translated)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).strip().lower()


def canonicalize_match_url(match_url: str) -> str:
    """Supprime les espaces et la barre finale '/' pour une déduplication stable."""
    return (match_url or "").strip().rstrip("/")


def extract_match_id(match_url: str) -> str:
    """Extrait l'identifiant numérique TennisInsight depuis une URL de match."""
    match = _MATCH_ID_RE.search(match_url or "")
    return match.group(1) if match else ""


async def fetch_with_retry(
    session: aiohttp.ClientSession,
    url: str,
    method: str = "GET",
    data: Any = None,
    attempts: int = 3,
    backoff_step: float = 1.0,
) -> str:
    """Exécute une requête HTTP asynchrone avec backoff linéaire sur erreurs réseau."""
    method_upper = method.upper()
    for attempt in range(attempts):
        try:
            req = (
                session.get(url)
                if method_upper == "GET"
                else session.post(url, data=data)
            )
            async with req as response:
                if response.status == 200:
                    text = await response.text()
                    if text and text.strip():
                        return text
        except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError, OSError):
            pass
        if attempt < attempts - 1:
            await asyncio.sleep(backoff_step * (attempt + 1))
    return ""


def parse_english_date(date_str: str) -> datetime:
    """Parse une date anglaise ('May 01 2026') indépendamment de la locale système."""
    cleaned = (date_str or "").strip()
    match = _EN_DATE_RE.match(cleaned)
    if not match:
        raise ValueError(f"Format de date anglais invalide : {date_str!r}")
    month_key = match.group(1)[:3].lower()
    month = _EN_MONTHS.get(month_key)
    if month is None:
        raise ValueError(f"Mois anglais inconnu : {match.group(1)!r}")
    return datetime(int(match.group(3)), month, int(match.group(2)))


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
        parsed_ts = parse_english_date(show_class[date_i].text).timestamp()
        return (today - parsed_ts) <= one_month

    @staticmethod
    def is_within_last_month(
        show_class: Sequence, date_i: int, today: float, one_month: int
    ) -> bool:
        """Vérifie si l'horodatage à date_i est dans la fenêtre d'un mois."""
        parsed_ts = parse_english_date(show_class[date_i].text).timestamp()
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
                parse_english_date(show_class[date_i].text)
                return date_i
            except (ValueError, IndexError):
                date_i -= 1
        return 0


def get_arg(args: Sequence[Any], index: int, fallback: Optional[Any] = None) -> Any:
    """Récupère un élément positionnel dans args si disponible, sinon fallback."""
    return args[index] if len(args) > index else fallback
