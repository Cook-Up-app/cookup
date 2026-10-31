from decimal import Decimal

from apps.catalog.normalization import parse_line, to_base
from apps.shopping.aggregation import IngredientInfo, MealNeed, RecipeLine


def line(text: str, ingredient_id: int | None = None, optional: bool = False) -> RecipeLine:
    """Ligne de recette depuis un texte français, comme la normalisation du catalogue."""
    parsed = parse_line(text)
    quantity, unit = to_base(parsed.quantity, parsed.unit)
    return RecipeLine(
        ingredient_id, parsed.name or text, quantity, unit, optional or parsed.is_optional
    )


def need(*texts, recipe_id="r1", title="Recette", servings=4, cook=4, ids=None) -> MealNeed:
    ids = ids or {}
    lines = [line(t, ids.get(t)) for t in texts]
    return MealNeed(recipe_id, title, servings, cook, lines)


def infos(**names) -> dict[int, IngredientInfo]:
    """infos(huile=dict(id=1, name="huile d'olive"), ...) -> {id: IngredientInfo}"""
    return {v["id"]: IngredientInfo(**v) for v in names.values()}


D = Decimal
