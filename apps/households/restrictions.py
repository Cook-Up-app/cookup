"""Ce que désigne une restriction alimentaire, et reconnaissance d'un texte saisi (fonctions pures).

Une allergie doit être fiable : un mot est d'abord cherché parmi les allergènes officiels, puis les
familles d'aliments, puis le catalogue ; sinon il est gardé tel quel et signalé comme tel. La
comparaison ignore accents, casse et pluriel (« légumineuse », « Légumineuses » : même chose).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from functools import cache

from apps.catalog.text import stem_key
from apps.core.lexicon import ALLERGEN_SYNONYMS, FOOD_GROUPS
from apps.core.reference import Allergen, FoodGroup

TERM_SEPARATOR = re.compile(r"[,;\n]+")
MAX_TERMS = 10
MAX_TERM_LENGTH = 100
MEMBERS_SHOWN = 6  # aliments cités pour décrire une famille


class Kind(StrEnum):
    ALLERGEN = "allergen"
    GROUP = "group"
    INGREDIENT = "ingredient"
    FREE = "free"


@dataclass(frozen=True)
class Target:
    """Ce que le texte saisi désigne : un code (allergène, famille) ou un nom d'aliment."""

    kind: Kind
    value: str
    typed: str = ""

    @property
    def known(self) -> bool:
        return self.kind is not Kind.FREE


@dataclass(frozen=True)
class Coverage:
    """Ce qu'une restriction exclut : allergènes déclarés et jeux de mots à retrouver."""

    allergens: frozenset[str] = frozenset()
    word_sets: frozenset[frozenset[str]] = frozenset()


def word_set(text: str) -> frozenset[str]:
    return frozenset(stem_key(text).split())


@cache
def group_coverage(group: str) -> Coverage:
    definition = FOOD_GROUPS[FoodGroup(group)]
    return Coverage(
        allergens=frozenset(a.value for a in definition.allergens),
        word_sets=frozenset(word_set(member) for member in definition.members),
    )


def coverage(allergen: str = "", food_group: str = "", ingredient_name: str = "") -> Coverage:
    """Exclusion d'une restriction ; les trois cibles s'additionnent."""
    parts = [Coverage(allergens=frozenset({allergen}))] if allergen else []
    if food_group:
        parts.append(group_coverage(food_group))
    if word_set(ingredient_name):
        parts.append(Coverage(word_sets=frozenset({word_set(ingredient_name)})))
    return Coverage(
        allergens=frozenset().union(*(p.allergens for p in parts)),
        word_sets=frozenset().union(*(p.word_sets for p in parts)),
    )


def group_examples(group: str) -> str:
    """Quelques aliments de la famille, pour montrer ce qui sera exclu."""
    members = FOOD_GROUPS[FoodGroup(group)].members
    shown = ", ".join(members[:MEMBERS_SHOWN])
    return f"{shown}…" if len(members) > MEMBERS_SHOWN else shown


@cache
def _vocabulary() -> dict[str, tuple[Kind, str]]:
    """Clé comparable -> (type, code) ; les allergènes l'emportent sur les familles."""
    table: dict[str, tuple[Kind, str]] = {}
    for group, definition in FOOD_GROUPS.items():
        for label in (str(group.label), *definition.synonyms):
            table[stem_key(label)] = (Kind.GROUP, group.value)
    for allergen, synonyms in ALLERGEN_SYNONYMS.items():
        for label in (str(allergen.label), *synonyms):
            table[stem_key(label)] = (Kind.ALLERGEN, allergen.value)
    return table


def split_terms(text: str) -> list[str]:
    """Découpe une saisie « lentilles, noix ; ail » en termes propres, sans doublon."""
    seen: dict[str, str] = {}
    for raw in TERM_SEPARATOR.split(text or ""):
        term = " ".join(raw.split())[:MAX_TERM_LENGTH]
        if term:
            seen.setdefault(stem_key(term), term)
    return list(seen.values())[:MAX_TERMS]


def recognise(term: str, catalog_name: Callable[[str], str | None]) -> Target:
    """Allergène, famille ou aliment du catalogue ; à défaut, texte libre (cherché dans le texte).

    `catalog_name` renvoie le nom canonique d'un ingrédient exactement reconnu, sinon None.
    """
    found = _vocabulary().get(stem_key(term))
    if found is not None:
        return Target(found[0], found[1], typed=term)
    name = catalog_name(term)
    if name:
        return Target(Kind.INGREDIENT, name, typed=term)
    return Target(Kind.FREE, " ".join(term.split()), typed=term)


def describe(target: Target) -> str:
    """Phrase qui dit ce qui a été retenu, surtout quand c'est plus large que le mot saisi."""
    if target.kind is Kind.ALLERGEN:
        label = str(Allergen(target.value).label)
        if stem_key(target.typed) in {"", stem_key(label)}:
            return label
        return (
            f"« {target.typed} » : classé dans « {label} » (tout ce groupe est exclu, par prudence)"
        )
    if target.kind is Kind.GROUP:
        label = str(FoodGroup(target.value).label)
        return f"{label} : exclut {group_examples(target.value)}"
    if target.kind is Kind.INGREDIENT:
        return target.value
    return (
        f"« {target.typed} » n'est pas dans notre catalogue : seul le texte des recettes sera "
        "vérifié, soyez attentif aux étiquettes"
    )
