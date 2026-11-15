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
