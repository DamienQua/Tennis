"""Identités de joueurs normalisées, sans rapprochement approximatif des homonymes."""

import re
import unicodedata


_ALIASES = {
    "cori gauff": "coco gauff",
    "albert ramos vinolas": "albert ramos",
    "holger vitus nodskov rune": "holger rune",
}


def canonical_name(name: str) -> str:
    """Normalise casse, accents et ponctuation, puis applique les alias connus."""
    decomposed = unicodedata.normalize("NFKD", name or "").casefold()
    letters = "".join(char for char in decomposed if not unicodedata.combining(char))
    normalized = " ".join(re.sub(r"[^\w\s]|_", " ", letters).split())
    return _ALIASES.get(normalized, normalized)


def names_match(first: str, second: str) -> bool:
    """Accepte uniquement une identité complète normalisée identique et non vide."""
    first_name = canonical_name(first)
    return bool(first_name) and first_name == canonical_name(second)
