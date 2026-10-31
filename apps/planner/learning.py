"""Apprentissage des goûts à partir des notes de recettes (fonctions pures)."""

from collections import defaultdict
from collections.abc import Mapping

PRIOR_WEIGHT = 2.0  # poids d'« observations neutres » : peu de notes, peu de conclusions
MAX_TASTE = 2.0  # même échelle que les goûts saisis (de -2 à +2)
MIDDLE_RATING = 3.0


def learn_tastes(
    ratings: Mapping[str, int], recipe_ingredients: Mapping[str, frozenset[int]]
) -> dict[int, float]:
    """Affinité de -2 à +2 par ingrédient, d'après l'écart entre la note et la note habituelle.

    On compare chaque note à la moyenne du foyer (lissée vers 3) pour qu'un foyer qui note tout
    à 4 ne trouve pas tout meilleur ; l'écart est réparti sur les ingrédients de la recette puis
    atténué tant qu'un ingrédient a été vu dans peu de recettes notées.
    """
    rated = {rid: score for rid, score in ratings.items() if rid in recipe_ingredients}
    if not rated:
        return {}
    centre = (sum(rated.values()) + MIDDLE_RATING * PRIOR_WEIGHT) / (len(rated) + PRIOR_WEIGHT)
    deviation: dict[int, float] = defaultdict(float)
    seen: dict[int, int] = defaultdict(int)
    for recipe_id, score in rated.items():
        for ingredient_id in recipe_ingredients[recipe_id]:
            deviation[ingredient_id] += score - centre
            seen[ingredient_id] += 1
    return {
        ingredient_id: max(-MAX_TASTE, min(MAX_TASTE, total / (seen[ingredient_id] + PRIOR_WEIGHT)))
        for ingredient_id, total in deviation.items()
        if abs(total) > 0
    }
