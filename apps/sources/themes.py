"""Thèmes de recherche automatique : tournent chaque semaine pour varier le catalogue."""

DEFAULT_THEMES: tuple[str, ...] = (
    "poulet rôti", "gratin dauphinois", "soupe de légumes", "pâtes carbonara", "quiche lorraine",
    "curry de légumes", "lasagnes", "poisson au four", "risotto", "salade composée",
    "crêpes", "gâteau au chocolat", "tarte aux pommes", "pot-au-feu", "blanquette de veau",
    "ratatouille", "couscous", "chili con carne", "omelette", "croque-monsieur",
    "pizza maison", "boulettes de viande", "riz cantonais", "tajine de poulet", "hachis parmentier",
    "velouté de potimarron", "wok de légumes", "porridge", "pain perdu", "muffins",
    "cookeo poulet", "cookeo légumes", "cookeo riz", "cookeo soupe", "cookeo pâtes",
    "cookeo poisson", "cookeo viande", "cookeo dessert", "cookeo plat complet", "cookeo gratin",
    "repas végétarien", "plat rapide 20 minutes", "plat unique", "salade de pâtes", "tarte salée",
    "saumon", "poulet curry", "bœuf bourguignon", "gratin de courgettes", "pâtes aux légumes",
    "soupe de poisson", "clafoutis", "mousse au chocolat", "salade de fruits", "yaourt gâteau",
    "petit déjeuner", "goûter enfants", "cake salé", "flan", "purée maison",
)  # fmt: skip


def themes_for_week(
    iso_week: int, count: int, themes: tuple[str, ...] = DEFAULT_THEMES
) -> list[str]:
    """`count` thèmes consécutifs, décalés d'une semaine à l'autre ; boucle sur la liste."""
    start = (iso_week * count) % len(themes)
    return [themes[(start + offset) % len(themes)] for offset in range(count)]
