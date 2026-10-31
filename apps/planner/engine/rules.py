"""Contraintes dures : une recette qui en viole une est écartée (SPEC section 7, étape 1)."""

from collections.abc import Callable
from datetime import timedelta
from enum import StrEnum

from .types import COOKEO_CAPACITY, MODE_CLASSIC, MODE_COOKEO, Context, RecipeView, SlotSpec


class Violation(StrEnum):
    ALLERGEN = "allergen"
    UNCERTAIN_ALLERGENS = "uncertain_allergens"
    DIET = "diet"
    UNCERTAIN_DIET = "uncertain_diet"
    EQUIPMENT = "equipment"
    SOURCE = "source"
    TIME = "time"
    MEAL_TYPE = "meal_type"
    PORTIONS = "portions"
    EXCLUDED = "excluded"
    RECENT = "recent"


Rule = Callable[[RecipeView, SlotSpec, Context], "Violation | None"]

# Un régime interdit si l'un de ces drapeaux figure sur la recette.
DIET_FORBIDDEN_FLAGS = {
    "vegetarian": {"meat", "fish"},
    "vegan": {"meat", "fish", "animal"},
    "pescatarian": {"meat"},
    "no_pork": {"pork"},
    "halal": {"pork", "alcohol"},
    "kosher": {"pork"},
}
KOSHER_FORBIDDEN_ALLERGENS = {"crustaceans", "molluscs"}


def _present(slot: SlotSpec, ctx: Context):
    return [ctx.diners[diner_id] for diner_id in slot.diner_ids]


def allergen_rule(recipe: RecipeView, slot: SlotSpec, ctx: Context) -> Violation | None:
    """Allergie stricte : exclusion totale ; dans le doute (ingrédient inconnu), exclusion aussi."""
    diners = _present(slot, ctx)
    strict = set().union(*(d.strict_allergens for d in diners)) if diners else set()
    word_sets = [ws for d in diners for ws in d.strict_word_sets]
    if strict & recipe.allergens or any(words <= recipe.words for words in word_sets):
        return Violation.ALLERGEN
    if (strict or word_sets) and not recipe.allergens_certain:
        return Violation.UNCERTAIN_ALLERGENS
    return None


def diet_rule(recipe: RecipeView, slot: SlotSpec, ctx: Context) -> Violation | None:
    diets = set().union(*(d.diets for d in _present(slot, ctx))) if slot.diner_ids else set()
    for diet in diets:
        forbidden = DIET_FORBIDDEN_FLAGS.get(diet, set())
        if forbidden & recipe.diet_flags:
            return Violation.DIET
        if diet == "kosher" and KOSHER_FORBIDDEN_ALLERGENS & recipe.allergens:
            return Violation.DIET
        if diet == "kosher" and {"meat", "milk"} <= (recipe.diet_flags | recipe.allergens):
            return Violation.DIET
    if diets and not recipe.diet_certain:
        return Violation.UNCERTAIN_DIET
    return None


def equipment_rule(recipe: RecipeView, slot: SlotSpec, ctx: Context) -> Violation | None:
    owned = ctx.settings.equipment
    if (
        not recipe.required_equipment <= owned
        or recipe.required_equipment & slot.forbidden_equipment
    ):
        return Violation.EQUIPMENT
    return None


def source_rule(recipe: RecipeView, slot: SlotSpec, ctx: Context) -> Violation | None:
    if slot.mode == MODE_COOKEO and not recipe.cookeo:
        return Violation.SOURCE
    if slot.mode == MODE_CLASSIC and recipe.cookeo:
        return Violation.SOURCE
    return None


def time_rule(recipe: RecipeView, slot: SlotSpec, ctx: Context) -> Violation | None:
    limit = slot.max_minutes or (
        ctx.settings.max_minutes_weekend if slot.weekend else ctx.settings.max_minutes_weekday
    )
    if recipe.total_minutes is not None and recipe.total_minutes > limit:
        return Violation.TIME
    return None


def meal_type_rule(recipe: RecipeView, slot: SlotSpec, ctx: Context) -> Violation | None:
    return None if slot.meal_type in recipe.meal_types else Violation.MEAL_TYPE


def portions_rule(recipe: RecipeView, slot: SlotSpec, ctx: Context) -> Violation | None:
    over_capacity = recipe.cookeo and slot.cook_servings > COOKEO_CAPACITY
    if over_capacity and not ctx.settings.allow_cookeo_split:
        return Violation.PORTIONS
    return None


def excluded_rule(recipe: RecipeView, slot: SlotSpec, ctx: Context) -> Violation | None:
    return Violation.EXCLUDED if recipe.id in ctx.history.excluded else None


def recent_rule(recipe: RecipeView, slot: SlotSpec, ctx: Context) -> Violation | None:
    last = ctx.history.last_served.get(recipe.id)
    window = timedelta(days=ctx.settings.min_repeat_days)
    if last is not None and abs(slot.day - last) < window:
        return Violation.RECENT
    return None


# Ajouter une règle = l'ajouter ici (ouvert/fermé).
RULES: tuple[Rule, ...] = (
    allergen_rule,
    diet_rule,
    equipment_rule,
    source_rule,
    time_rule,
    meal_type_rule,
    portions_rule,
    excluded_rule,
    recent_rule,
)


def violations(recipe: RecipeView, slot: SlotSpec, ctx: Context) -> list[Violation]:
    return [found for rule in RULES if (found := rule(recipe, slot, ctx)) is not None]


def is_allowed(recipe: RecipeView, slot: SlotSpec, ctx: Context) -> bool:
    return all(rule(recipe, slot, ctx) is None for rule in RULES)
