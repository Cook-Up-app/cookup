"""Repli de texte partagé par la normalisation et la recherche (source unique)."""

import re
import unicodedata

_LIGATURES = str.maketrans({"œ": "oe", "Œ": "oe", "æ": "ae", "Æ": "ae"})
_NON_ALNUM = re.compile(r"[^a-z0-9/]+")
# Mots invariables au pluriel ou dont le « s » final fait partie du nom.
_INVARIABLE = frozenset({"pois", "mais", "riz", "anis", "ananas", "cassis", "maïs", "radis"})
STOPWORDS = frozenset(
    {"de", "d", "du", "des", "la", "le", "les", "l", "au", "aux", "a", "et", "en"}
)


def fold(text: str) -> str:
    """Minuscules, sans accents ni ponctuation, espaces simples."""
    text = text.translate(_LIGATURES).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _NON_ALNUM.sub(" ", text).strip()


def singular(word: str) -> str:
    if len(word) > 3 and word not in _INVARIABLE and word[-1] in "sx":
        return word[:-1]
    return word


def stem_key(text: str) -> str:
    """Clé de comparaison : repliée, sans mots vides, au singulier."""
    words = [singular(w) for w in fold(text).split() if w not in STOPWORDS]
    return " ".join(words)
