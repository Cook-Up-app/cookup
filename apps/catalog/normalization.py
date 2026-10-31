"""Analyse des lignes d'ingrédients françaises : quantité, unité, nom (fonctions pures)."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from apps.core.units import BASE_UNIT_CODE, UNITS_BY_ALIAS, Unit, UnitKind

from .text import STOPWORDS, fold

_FRACTIONS = str.maketrans({"½": " 1/2", "¼": " 1/4", "¾": " 3/4", "⅓": " 1/3", "⅔": " 2/3"})
_NUMBER = r"\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?"
_RANGE = re.compile(rf"^\s*({_NUMBER})\s*(?:à|a|-|–|ou)\s*({_NUMBER})(?!\d)", re.I)
_SINGLE = re.compile(rf"^\s*({_NUMBER})")
_PARENTHESES = re.compile(r"\([^)]*\)")
_OPTIONAL = re.compile(r"\b(?:facultatif|facultative|optionnel|optionnelle)\b", re.I)
_GLUED_UNIT = re.compile(r"(?<=\d)(?=[a-zA-Zà-ÿ])")
_DESCRIPTOR_COMMA = re.compile(r",(?!\d)")  # « farine, tamisée » mais pas « 1,5 »
_VAGUE_PREFIXES = ("un peu de", "un peu d'", "quelques", "une touche de", "une louche de")
_ONE_WORDS = frozenset({"un", "une"})
_HALF_WORDS = frozenset({"demi", "demie"})
MAX_UNIT_TOKENS = 3


@dataclass(frozen=True)
class ParsedLine:
    raw_text: str
    quantity: Decimal | None
    unit: Unit | None
    name: str  # texte restant, accents conservés
    is_optional: bool


def _to_decimal(token: str) -> Decimal | None:
    total = Decimal(0)
    try:
        for part in token.replace(",", ".").split():
            if "/" in part:
                numerator, denominator = part.split("/")
                total += Decimal(numerator) / Decimal(denominator)
            else:
                total += Decimal(part)
    except (InvalidOperation, ZeroDivisionError):
        return None
    return total


def _take_quantity(text: str) -> tuple[Decimal | None, str]:
    """Une fourchette (« 2 à 3 ») garde la borne haute, pour ne pas manquer d'ingrédient."""
    for prefix in _VAGUE_PREFIXES:
        if text.lower().startswith(prefix):
            return None, text[len(prefix) :]
    if match := _RANGE.match(text):
        return _to_decimal(match.group(2)), text[match.end() :]
    if match := _SINGLE.match(text):
        return _to_decimal(match.group(1)), text[match.end() :]
    first, _, rest = text.strip().partition(" ")
    if first.lower() in _ONE_WORDS:
        return Decimal(1), rest
    if first.lower() in _HALF_WORDS:
        return Decimal("0.5"), rest
    return None, text


def _tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[\s'’.]+", text) if token]


def _take_unit(tokens: list[str]) -> tuple[Unit | None, list[str]]:
    folded = [fold(token) for token in tokens]
    for size in range(min(MAX_UNIT_TOKENS, len(tokens)), 0, -1):
        unit = UNITS_BY_ALIAS.get(" ".join(folded[:size]).strip())
        if unit is not None:
            return unit, tokens[size:]
    return None, tokens


def _strip_leading_stopwords(tokens: list[str]) -> list[str]:
    start = 0
    while start < len(tokens) and fold(tokens[start]) in STOPWORDS:
        start += 1
    return tokens[start:]


def parse_line(line: str) -> ParsedLine:
    """Ex. « 2 c. à soupe d'huile d'olive » → 2, c. à soupe, « huile d olive »."""
    text = line.translate(_FRACTIONS).replace("\xa0", " ").strip()
    is_optional = bool(_OPTIONAL.search(text))
    text = _OPTIONAL.sub(" ", _PARENTHESES.sub(" ", text))
    text = _DESCRIPTOR_COMMA.split(_GLUED_UNIT.sub(" ", text))[0]
    quantity, rest = _take_quantity(text)
    unit, tokens = _take_unit(_tokens(rest))
    name = " ".join(_strip_leading_stopwords(tokens))
    return ParsedLine(line.strip(), quantity, unit, name, is_optional)


def split_compound(line: str) -> list[str]:
    """« Sel, poivre » désigne deux ingrédients sans quantité ; avec un chiffre, un seul."""
    if any(char.isdigit() for char in line) or "," not in line:
        return [line]
    return [part.strip() for part in line.split(",") if part.strip()]


def to_base(quantity: Decimal | None, unit: Unit | None) -> tuple[Decimal | None, str]:
    """Quantité en unité de base (g, ml, pièce) ; vide pour les unités non convertibles."""
    if quantity is None:
        return None, ""
    if unit is None:
        return quantity, BASE_UNIT_CODE[UnitKind.COUNT]
    if unit.kind is UnitKind.UNCOUNTED:
        return None, ""
    return quantity * unit.to_base, BASE_UNIT_CODE[unit.kind]
