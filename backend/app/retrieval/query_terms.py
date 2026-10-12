"""Turns a French or English message into English MedlinePlus search terms (config/medical_terms.yml)."""
import re
from typing import List, Pattern, Tuple

from app.core import config_loader

_CONFIG = config_loader.medical_terms()

# Word boundaries keep "burn" from matching "heartburn"; an optional plural "s" is allowed.
_PATTERNS: List[Tuple[str, Pattern]] = [
    (entry.term, re.compile(r"\b(" + "|".join(re.escape(p) for p in entry.phrases) + r")s?\b", re.IGNORECASE))
    for entry in _CONFIG.terms
]


def search_terms(text: str) -> List[str]:
    """English search terms for the symptoms mentioned in `text`, most urgent first."""
    text = text.replace("’", "'")
    return [term for term, pattern in _PATTERNS if pattern.search(text)][:_CONFIG.max_terms]
