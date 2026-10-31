"""Unités et conversions : source unique pour la normalisation et la liste de courses."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class UnitKind(StrEnum):
    MASS = "mass"  # base : g
    VOLUME = "volume"  # base : ml
    COUNT = "count"  # comptage, propre à l'ingrédient
    UNCOUNTED = "uncounted"  # pincée, noix, filet… : non convertie


@dataclass(frozen=True)
class Unit:
    code: str
    kind: UnitKind
    to_base: Decimal  # facteur vers g, ml, ou 1 pour le comptage
    aliases: tuple[str, ...]


def _unit(code: str, kind: UnitKind, factor: str, *aliases: str) -> Unit:
    return Unit(code, kind, Decimal(factor), aliases)


# Les alias sont écrits sans accents ni ponctuation (voir `normalization.fold`).
UNITS: tuple[Unit, ...] = (
    _unit("g", UnitKind.MASS, "1", "g", "gr", "gramme", "grammes"),
    _unit("kg", UnitKind.MASS, "1000", "kg", "kilo", "kilos", "kilogramme", "kilogrammes"),
    _unit("ml", UnitKind.VOLUME, "1", "ml", "millilitre", "millilitres"),
    _unit("cl", UnitKind.VOLUME, "10", "cl", "centilitre", "centilitres"),
    _unit("dl", UnitKind.VOLUME, "100", "dl", "decilitre", "decilitres"),
    _unit("l", UnitKind.VOLUME, "1000", "l", "litre", "litres"),
    _unit(
        "c. à café",
        UnitKind.VOLUME,
        "5",
        "c a c",
        "cac",
        "c a cafe",
        "cuillere a cafe",
        "cuilleres a cafe",
    ),
    _unit(
        "c. à soupe",
        UnitKind.VOLUME,
        "15",
        "c a s",
        "cas",
        "c a soupe",
        "cuillere a soupe",
        "cuilleres a soupe",
    ),
    _unit("verre", UnitKind.VOLUME, "200", "verre", "verres"),
    _unit("tasse", UnitKind.VOLUME, "250", "tasse", "tasses"),
    _unit("pièce", UnitKind.COUNT, "1", "piece", "pieces"),
    _unit("gousse", UnitKind.COUNT, "1", "gousse", "gousses"),
    _unit("tranche", UnitKind.COUNT, "1", "tranche", "tranches"),
    _unit("sachet", UnitKind.COUNT, "1", "sachet", "sachets"),
    _unit("boîte", UnitKind.COUNT, "1", "boite", "boites"),
    _unit("pot", UnitKind.COUNT, "1", "pot", "pots"),
    _unit("brin", UnitKind.COUNT, "1", "brin", "brins"),
    _unit("feuille", UnitKind.COUNT, "1", "feuille", "feuilles"),
    _unit("branche", UnitKind.COUNT, "1", "branche", "branches"),
    _unit("botte", UnitKind.COUNT, "1", "botte", "bottes"),
    _unit("bouquet", UnitKind.COUNT, "1", "bouquet", "bouquets"),
    _unit("morceau", UnitKind.COUNT, "1", "morceau", "morceaux"),
    _unit("cube", UnitKind.COUNT, "1", "cube", "cubes"),
    _unit("pincée", UnitKind.UNCOUNTED, "1", "pincee", "pincees"),
    _unit("noix", UnitKind.UNCOUNTED, "1", "noix"),
    _unit("filet", UnitKind.UNCOUNTED, "1", "filet", "filets"),
    _unit("poignée", UnitKind.UNCOUNTED, "1", "poignee", "poignees"),
)

UNITS_BY_CODE = {unit.code: unit for unit in UNITS}
UNITS_BY_ALIAS = {alias: unit for unit in UNITS for alias in unit.aliases}

# Unité de base par type : g, ml, ou comptage.
BASE_UNIT_CODE = {UnitKind.MASS: "g", UnitKind.VOLUME: "ml", UnitKind.COUNT: "pièce"}
