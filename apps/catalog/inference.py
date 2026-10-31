"""Déductions simples à partir des métadonnées d'une source (type de repas, difficulté)."""

from apps.core.reference import MealType

from .text import fold

_CATEGORY_RULES: tuple[tuple[tuple[str, ...], tuple[MealType, ...]], ...] = (
    (("dessert", "gateau", "patisserie", "confiserie"), (MealType.DESSERT,)),
    (("petit dejeuner", "petit-dejeuner", "brunch"), (MealType.BREAKFAST,)),
    (("gouter", "collation", "snack"), (MealType.SNACK,)),
)
_DEFAULT_MEAL_TYPES = (MealType.LUNCH, MealType.DINNER)


def infer_meal_types(*labels: str) -> list[str]:
    """Types de repas depuis des libellés (catégorie, étiquettes) ; déjeuner et dîner par défaut."""
    text = " ".join(fold(label) for label in labels if label)
    found: list[str] = []
    for keywords, meal_types in _CATEGORY_RULES:
        if any(keyword in text for keyword in keywords):
            found.extend(m for m in meal_types if m not in found)
    return found or [m.value for m in _DEFAULT_MEAL_TYPES]
