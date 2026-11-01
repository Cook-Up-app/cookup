"""Critère « styles de cuisine » : cuisines aimées ou évitées, piment, goût d'ailleurs.

Un style ne fait que pousser ou freiner une recette : il n'exclut jamais (réservé aux allergies).
"""

from .criteria import NEUTRAL, criterion
from .types import Context, RecipeView, SlotSpec

LIKED, AVOIDED = 1.0, 0.0
SPICE_PENALTY_PER_LEVEL = 0.25  # par cran de piment au-dessus de la tolérance
WITHIN_TOLERANCE = 0.6  # recette épicée mais acceptée : légèrement favorable
EXOTIC_SCORES = (0.0, NEUTRAL, 1.0)  # selon `exoticism` : évite, neutre, recherche
FAMILIAR_SCORES = (0.7, NEUTRAL, NEUTRAL)  # recette familière, selon `exoticism`


def _cuisine_part(recipe: RecipeView, ctx: Context) -> float | None:
    if recipe.cuisine in ctx.settings.liked_cuisines:
        return LIKED
    if recipe.cuisine in ctx.settings.avoided_cuisines:
        return AVOIDED
    return None


def _spice_part(recipe: RecipeView, ctx: Context) -> float | None:
    if recipe.spice == 0:
        return None
    excess = recipe.spice - ctx.settings.spice_tolerance
    if excess <= 0:
        return WITHIN_TOLERANCE
    return max(0.0, NEUTRAL - SPICE_PENALTY_PER_LEVEL * excess)


def _exotic_part(recipe: RecipeView, ctx: Context) -> float | None:
    scores = EXOTIC_SCORES if recipe.exotic else FAMILIAR_SCORES
    score = scores[ctx.settings.exoticism]
    return None if score == NEUTRAL else score


@criterion
class StyleCriterion:
    name = "style"
    default_weight = 10

    def score(self, recipe: RecipeView, slot: SlotSpec, ctx: Context, state) -> float:
        parts = [
            part
            for part in (
                _cuisine_part(recipe, ctx),
                _spice_part(recipe, ctx),
                _exotic_part(recipe, ctx),
            )
            if part is not None
        ]
        return sum(parts) / len(parts) if parts else NEUTRAL

    def explain(self, recipe: RecipeView, slot: SlotSpec, ctx: Context, state) -> str | None:
        if recipe.cuisine in ctx.settings.liked_cuisines:
            label = ctx.settings.cuisine_labels.get(recipe.cuisine, recipe.cuisine)
            return f"cuisine {label.lower()} appréciée"
        return None
