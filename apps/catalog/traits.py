"""Traits alimentaires dérivés du catalogue : régimes et groupe de protéine (fonctions pures)."""

from apps.core.reference import Aisle, Allergen

from .text import stem_key

MEAT = {
    "poulet", "dinde", "bœuf", "bœuf haché", "veau", "porc", "lardons", "jambon", "jambon cru",
    "saucisse", "chorizo", "merguez", "canard", "agneau", "bouillon de volaille",
    "bouillon de bœuf", "bouillon",
}  # fmt: skip
PORK = {"porc", "lardons", "jambon", "jambon cru", "saucisse", "chorizo"}
ALCOHOL = {"vin blanc", "vin rouge", "bière"}
PLANT_DAIRY = {"lait d'amande", "boisson soja"}
PROTEIN_GROUPS = {
    "volaille": {"poulet", "dinde", "canard", "bouillon de volaille"},
    "viande rouge": {"bœuf", "bœuf haché", "veau", "agneau", "merguez", "bouillon de bœuf"},
    "porc": PORK,
    "œuf": {"œuf"},
    "légumineuses": {"pois chiches", "lentilles", "haricots rouges"},
}
FISH_ALLERGENS = {Allergen.FISH, Allergen.CRUSTACEANS, Allergen.MOLLUSCS}
ANIMAL_ALLERGENS = FISH_ALLERGENS | {Allergen.MILK, Allergen.EGGS}
PERISHABLE_AISLES = {Aisle.FRUITS_VEGETABLES, Aisle.BUTCHER_FISH, Aisle.DAIRY}
PROTEIN_SEAFOOD = "poisson et fruits de mer"


def _keys(names: set[str]) -> set[str]:
    return {stem_key(name) for name in names}


_MEAT, _PORK, _ALCOHOL, _PLANT = _keys(MEAT), _keys(PORK), _keys(ALCOHOL), _keys(PLANT_DAIRY)
_GROUPS = {group: _keys(names) for group, names in PROTEIN_GROUPS.items()}


def diet_flags(name: str, aisle: str, allergens: list[str]) -> list[str]:
    """Drapeaux : meat, fish, pork, animal (produit animal), alcohol."""
    key = stem_key(name)
    flags: set[str] = set()
    if key in _MEAT:
        flags |= {"meat", "animal"}
    if key in _PORK:
        flags.add("pork")
    if key in _ALCOHOL:
        flags.add("alcohol")
    if set(allergens) & FISH_ALLERGENS:
        flags |= {"fish", "animal"}
    if set(allergens) & ANIMAL_ALLERGENS and key not in _PLANT:
        flags.add("animal")
    if aisle == Aisle.DAIRY and key not in _PLANT or key == stem_key("miel"):
        flags.add("animal")
    return sorted(flags)


def protein_group(name: str, allergens: list[str]) -> str:
    key = stem_key(name)
    if set(allergens) & FISH_ALLERGENS:
        return PROTEIN_SEAFOOD
    for group, keys in _GROUPS.items():
        if key in keys:
            return group
    return ""


def is_perishable(aisle: str) -> bool:
    return aisle in PERISHABLE_AISLES
