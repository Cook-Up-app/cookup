"""Score souple de 0 à 100 : un critère = une classe enregistrée (SPEC section 7, étape 2)."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from .types import Context, RecipeView, SlotSpec

WEEKDAYS_FR = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
NEUTRAL = 0.5
MAX_TASTE = 2  # les goûts vont de -2 à +2
LIKED_THRESHOLD = 0.5  # moyenne des goûts à partir de laquelle on cite « aimé par »


@dataclass
class PlanState:
    """Recettes déjà placées, pour les critères qui dépendent du reste du menu."""

    placed: dict[str, tuple[SlotSpec, RecipeView]] = field(default_factory=dict)

    def others(self, slot: SlotSpec) -> list[tuple[SlotSpec, RecipeView]]:
        return [item for key, item in self.placed.items() if key != slot.key]

    def previous(self, slot: SlotSpec) -> RecipeView | None:
        earlier = [
            (other.order, recipe) for other, recipe in self.others(slot) if other.order < slot.order
        ]
        return max(earlier, key=lambda item: item[0])[1] if earlier else None


class Criterion(Protocol):
    name: str
    default_weight: int

    def score(
        self, recipe: RecipeView, slot: SlotSpec, ctx: Context, state: PlanState
    ) -> float: ...

    def explain(
        self, recipe: RecipeView, slot: SlotSpec, ctx: Context, state: PlanState
    ) -> str | None: ...


CRITERIA: dict[str, Criterion] = {}


def criterion(cls: type) -> type:
    CRITERIA[cls.name] = cls()
    return cls


def _taste_of(recipe: RecipeView, taste: Mapping[int, int]) -> float:
    values = [taste[i] for i in recipe.ingredient_ids if i in taste]
    return sum(values) / len(values) if values else 0.0


@criterion
class TasteCriterion:
    """Moyenne des goûts, pénalisée par le convive qui aime le moins la recette."""

    name = "taste"
    default_weight = 30

    def _means(self, recipe, slot, ctx) -> dict[str, float]:
        return {i: _taste_of(recipe, ctx.diners[i].taste) for i in slot.diner_ids}

    def score(self, recipe, slot, ctx, state) -> float:
        means = self._means(recipe, slot, ctx)
        wanted = 0.2 if ctx.settings.wanted_tags & recipe.tags else 0.0
        if not means:
            return min(1.0, NEUTRAL + wanted)
        normalised = [(m + MAX_TASTE) / (2 * MAX_TASTE) for m in means.values()]
        blend = 0.5 * sum(normalised) / len(normalised) + 0.5 * min(normalised)
        return min(1.0, blend + wanted)

    def explain(self, recipe, slot, ctx, state) -> str | None:
        fans = [
            ctx.diners[i].name
            for i, m in self._means(recipe, slot, ctx).items()
            if m >= LIKED_THRESHOLD
        ]
        return f"aimé par {_join(fans)}" if fans else None


@criterion
class RatingCriterion:
    name = "rating"
    default_weight = 15

    def score(self, recipe, slot, ctx, state) -> float:
        if recipe.id in ctx.history.favorites:
            return 1.0
        rating = ctx.history.ratings.get(recipe.id)
        return (rating - 1) / 4 if rating else NEUTRAL

    def explain(self, recipe, slot, ctx, state) -> str | None:
        if recipe.id in ctx.history.favorites:
            return "un de vos favoris"
        rating = ctx.history.ratings.get(recipe.id)
        return f"notée {rating}/5" if rating and rating >= 4 else None  # noqa: PLR2004


@criterion
class FreshnessCriterion:
    name = "freshness"
    default_weight = 20

    def score(self, recipe, slot, ctx, state) -> float:
        last = ctx.history.last_served.get(recipe.id)
        if last is None:
            return 1.0
        horizon = max(1, 2 * ctx.settings.min_repeat_days)
        return min(1.0, abs((slot.day - last).days) / horizon)

    def explain(self, recipe, slot, ctx, state) -> str | None:
        return None  # toujours vrai après le filtre dur : n'apprend rien à l'utilisateur


@criterion
class DiversityCriterion:
    """Ni la même protéine ni la même cuisine deux repas de suite ; quota de repas végétariens."""

    name = "diversity"
    default_weight = 15

    def _vegetarian_unmet(self, ctx, state, slot) -> bool:
        quota = ctx.settings.vegetarian_per_week
        done = sum(1 for _, r in state.others(slot) if r.vegetarian)
        return done < quota

    def score(self, recipe, slot, ctx, state) -> float:
        score = 1.0
        previous = state.previous(slot)
        if previous is not None:
            if recipe.protein and recipe.protein == previous.protein:
                score -= 0.5
            if recipe.cuisine and recipe.cuisine == previous.cuisine:
                score -= 0.3
        if self._vegetarian_unmet(ctx, state, slot) and not recipe.vegetarian:
            score -= 0.2
        return max(0.0, score)

    def explain(self, recipe, slot, ctx, state) -> str | None:
        if recipe.vegetarian and self._vegetarian_unmet(ctx, state, slot):
            return "repas végétarien de la semaine"
        previous = state.previous(slot)
        if previous is not None and recipe.protein and recipe.protein != previous.protein:
            return "change du repas précédent"
        return None


@criterion
class AntiWasteCriterion:
    """Bonus aux recettes qui partagent des ingrédients périssables avec le reste du menu."""

    name = "antiwaste"
    default_weight = 10

    def _shared(self, recipe, slot, state) -> dict[int, SlotSpec]:
        shared: dict[int, SlotSpec] = {}
        for other_slot, other in state.others(slot):
            for ingredient in recipe.perishable_ids & other.perishable_ids:
                shared.setdefault(ingredient, other_slot)
        return shared

    def score(self, recipe, slot, ctx, state) -> float:
        if not recipe.perishable_ids:
            return 0.0
        return min(1.0, len(self._shared(recipe, slot, state)) / len(recipe.perishable_ids))

    def explain(self, recipe, slot, ctx, state) -> str | None:
        shared = self._shared(recipe, slot, state)
        if not shared:
            return None
        ingredient, other = sorted(shared.items())[0]
        name = ctx.ingredient_names.get(ingredient, "un ingrédient")
        return f"partage {name} avec le repas de {WEEKDAYS_FR[other.day.weekday()]}"


@criterion
class BudgetCriterion:
    name = "budget"
    default_weight = 5

    def score(self, recipe, slot, ctx, state) -> float:
        if recipe.cost_level is None:
            return 0.7
        over = recipe.cost_level - ctx.settings.budget_level
        return 1.0 if over <= 0 else (0.4 if over == 1 else 0.0)

    def explain(self, recipe, slot, ctx, state) -> str | None:
        ok = recipe.cost_level is not None and recipe.cost_level <= ctx.settings.budget_level
        return "dans le budget" if ok and recipe.cost_level == 1 else None


@criterion
class SeasonCriterion:
    name = "season"
    default_weight = 5

    def score(self, recipe, slot, ctx, state) -> float:
        if not recipe.produce_ids:
            return NEUTRAL
        return len(recipe.produce_ids & ctx.in_season_ids) / len(recipe.produce_ids)

    def explain(self, recipe, slot, ctx, state) -> str | None:
        return "de saison" if self.score(recipe, slot, ctx, state) >= 0.75 else None  # noqa: PLR2004


def weight_of(name: str, ctx: Context) -> int:
    return ctx.settings.weights.get(name, CRITERIA[name].default_weight)


def total_score(recipe: RecipeView, slot: SlotSpec, ctx: Context, state: PlanState) -> float:
    """Score pondéré de 0 à 100."""
    weights = {name: weight_of(name, ctx) for name in CRITERIA}
    total = sum(weights.values()) or 1
    return (
        100
        * sum(w * CRITERIA[n].score(recipe, slot, ctx, state) for n, w in weights.items())
        / total
    )


def explanation(recipe: RecipeView, slot: SlotSpec, ctx: Context, state: PlanState) -> str:
    """Phrase courte : « Aimé par Léa, 25 min, réutilise la crème liquide déjà prévue mardi »."""
    parts: list[str] = []
    for name in sorted(CRITERIA, key=lambda n: -weight_of(n, ctx)):
        text = CRITERIA[name].explain(recipe, slot, ctx, state)
        if text:
            parts.append(text)
    if recipe.total_minutes:
        parts.insert(min(1, len(parts)), f"{recipe.total_minutes} min")
    return (parts[0][0].upper() + ", ".join(parts)[1:] + ".") if parts else ""


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " et " + names[-1]


Scorer = Callable[[RecipeView, SlotSpec, Context, PlanState], float]
