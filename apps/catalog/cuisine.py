"""Style d'une recette (cuisine, piment) déduit du titre et des ingrédients (fonctions pures).

Une étiquette `cuisine:xxx` posée sur la recette prime ; sinon on compte les mots révélateurs.
Les mots sont écrits comme `stem_key` les produit (sans accent, au singulier).
"""

from apps.core.reference import EXOTIC_CUISINES, Cuisine

from .text import stem_key

CUISINE_WORDS: dict[Cuisine, frozenset[str]] = {
    Cuisine.ITALIAN: frozenset(
        [
            "spaghetti",
            "tagliatelle",
            "penne",
            "lasagne",
            "risotto",
            "parmesan",
            "mozzarella",
            "basilic",
            "pizza",
            "gnocchi",
            "ravioli",
            "pesto",
            "bolognaise",
            "carbonara",
            "tiramisu",
            "polenta",
            "ricotta",
        ]
    ),
    Cuisine.FRENCH: frozenset(
        [
            "gratin",
            "blanquette",
            "bourguignon",
            "quiche",
            "raclette",
            "tartiflette",
            "hachis",
            "ratatouille",
            "cassoulet",
            "confit",
            "croque",
            "vichyssoise",
            "gruyere",
        ]
    ),
    Cuisine.MEDITERRANEAN: frozenset(
        [
            "feta",
            "olive",
            "aubergine",
            "courgette",
            "poivron",
            "origan",
            "thym",
            "provencal",
            "houmou",
            "tzatziki",
            "tapenade",
            "sardine",
        ]
    ),
    Cuisine.ORIENTAL: frozenset(
        [
            "couscou",
            "semoule",
            "harissa",
            "tajine",
            "merguez",
            "falafel",
            "boulgour",
            "kebab",
            "taboule",
            "menthe",
        ]
    ),
    Cuisine.ASIAN: frozenset(
        [
            "soja",
            "gingembre",
            "nouille",
            "wok",
            "sesame",
            "teriyaki",
            "sushi",
            "coriandre",
            "citronnelle",
            "nem",
            "tofu",
            "miso",
        ]
    ),
    Cuisine.INDIAN: frozenset(
        ["curry", "curcuma", "garam", "naan", "dal", "dhal", "tikka", "masala", "biryani", "paneer"]
    ),
    Cuisine.MEXICAN: frozenset(
        [
            "tortilla",
            "guacamole",
            "chili",
            "fajita",
            "burrito",
            "taco",
            "nacho",
            "jalapeno",
            "enchilada",
        ]
    ),
}
SPICE_WORDS: dict[int, frozenset[str]] = {
    3: frozenset(
        ["piment", "harissa", "cayenne", "tabasco", "sambal", "jalapeno", "chili", "espelette"]
    ),
    2: frozenset(["curry", "garam", "gingembre", "masala", "cumin"]),
}
SPICY_TAG = "épicé"
MILD, MEDIUM, HOT = 1, 2, 3  # 0 : pas épicé


def _words(texts: list[str]) -> frozenset[str]:
    return frozenset(word for text in texts for word in stem_key(text).split())


def infer_cuisine(tags: frozenset[str], texts: list[str]) -> str:
    """Cuisine étiquetée, sinon la plus représentée dans les textes ; vide si rien n'est net."""
    for tag in sorted(tags):
        if tag.startswith("cuisine:") and tag.split(":", 1)[1] in Cuisine.values:
            return tag.split(":", 1)[1]
    words = _words(texts)
    scores = {cuisine: len(words & markers) for cuisine, markers in CUISINE_WORDS.items()}
    best = max(scores.values())
    if best == 0:
        return ""
    return next(cuisine.value for cuisine, score in scores.items() if score == best)


def spice_level(tags: frozenset[str], texts: list[str]) -> int:
    """0 (doux) à 3 (très piquant) selon les épices citées ; l'étiquette « épicé » vaut 2."""
    words = _words(texts)
    level = max((lvl for lvl, markers in SPICE_WORDS.items() if words & markers), default=0)
    return max(level, MEDIUM if SPICY_TAG in tags else 0)


def is_exotic(cuisine: str) -> bool:
    return bool(cuisine) and Cuisine(cuisine) in EXOTIC_CUISINES
