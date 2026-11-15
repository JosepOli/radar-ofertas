"""Normalización de texto para búsquedas: sin mayúsculas, sin tildes, términos independientes."""
from __future__ import annotations

import re
import unicodedata

_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text or "")
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return _SPACES.sub(" ", stripped.lower()).strip()


def matches_all_terms(haystack: str, query: str) -> bool:
    """True si cada término de la consulta aparece en el texto (en cualquier orden)."""
    hay = normalize(haystack)
    return all(term in hay for term in normalize(query).split())


_PAREN = re.compile(r"\([^)]*\)")
_TLD = re.compile(r"\.(?:es|com|eu|net|org|de|fr|it|pt|co\.uk)$")


def store_key(name: str) -> str:
    """Clave estable de una tienda: «www.PcComponentes.com» y «PcComponentes» comparten clave."""
    s = _PAREN.sub(" ", normalize(name))
    s = re.sub(r"^www\.", "", s.strip())
    s = _TLD.sub("", s)
    s = re.sub(r"\s+es$", "", s.strip())
    return re.sub(r"[\s.\-_]+", "", s)
