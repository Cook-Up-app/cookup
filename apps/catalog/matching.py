"""Rattachement d'un texte d'ingrédient au catalogue canonique (fonctions pures)."""

from dataclasses import dataclass

from .text import fold, stem_key

# Mots qui décrivent une préparation ou un état sans changer l'ingrédient (donc ni allergène).
HARMLESS_DESCRIPTORS = frozenset(
    {
        "entier", "frais", "fraiche", "rape", "rapee", "emince", "hache", "coupe",
        "morceau", "petit", "gros", "grosse", "moyen", "bio", "doux", "cru", "cuit", "cuite",
        "mur", "mure", "ferme", "fondu", "ramolli", "tamise", "pele", "epluche", "lave",
        "sec", "seche", "liquide", "fin", "fine", "nature", "maison", "vieux", "jeune",
        "concasse", "egoutte", "decongele", "surgele", "taille", "en", "cube",
        "lamelle", "rondelle", "tranche", "selon", "gout", "besoin", "environ", "bien",
        "vert", "verte", "rouge", "jaune", "blanc", "blanche", "noir", "noire", "gris",
    }
)  # fmt: skip


@dataclass(frozen=True)
class Match:
    ingredient_id: int
    exact: bool  # faux : correspondance partielle, à faire vérifier


class IngredientIndex:
    """Index en mémoire du catalogue (quelques centaines d'entrées, chargé une fois)."""

    def __init__(self, entries: list[tuple[int, str, list[str]]]) -> None:
        self._exact: dict[str, int] = {}
        for ingredient_id, name, aliases in entries:
            for label in (name, *aliases):
                self._exact.setdefault(stem_key(label), ingredient_id)
        self._by_length = sorted(self._exact, key=lambda key: -len(key.split()))

    def find(self, name: str) -> Match | None:
        key = stem_key(name)
        if not key:
            return None
        if key in self._exact:
            return Match(self._exact[key], exact=True)
        return self._find_contained(key.split())

    def _find_contained(self, words: list[str]) -> Match | None:
        for candidate in self._by_length:
            span = candidate.split()
            for start in range(len(words) - len(span) + 1):
                if words[start : start + len(span)] == span:
                    rest = words[:start] + words[start + len(span) :]
                    harmless = all(_is_harmless(word) for word in rest)
                    return Match(self._exact[candidate], exact=harmless)
        return None


def _is_harmless(word: str) -> bool:
    return word in HARMLESS_DESCRIPTORS or fold(word) in HARMLESS_DESCRIPTORS
