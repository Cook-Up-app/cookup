"""Frontière base de données : convertit le catalogue et le foyer en objets du moteur."""

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from apps.catalog.cuisine import infer_cuisine, is_exotic, spice_level
from apps.catalog.models import (
    Ingredient,
    Recipe,
    RecipeEquipment,
    RecipeFeedback,
    RecipeIngredient,
)
from apps.catalog.text import fold, singular
from apps.catalog.traits import is_perishable
from apps.core.reference import Aisle, Cuisine, Equipment
from apps.households import restrictions
from apps.households.models import (
    Diner,
    DinerRestriction,
    HouseholdEquipment,
    HouseholdSettings,
)

from .engine import Context, DinerView, EngineSettings, History, RecipeView
from .learning import learn_tastes
from .models import MenuSlot
from .seasons import seasonal_names

HISTORY_DAYS = 90
AVOID_SCORE = -2  # intolérance ou aliment évité : traité comme un goût très négatif
STRICT = DinerRestriction.Severity.STRICT_ALLERGY


def recipe_words(lines: list[str]) -> frozenset[str]:
    """Mots repliés et au singulier de toutes les lignes, pour les restrictions en texte libre."""
    return frozenset(singular(word) for line in lines for word in fold(line).split())


def _protein(groups: list[str]) -> str:
    counted = Counter(group for group in groups if group)
    return counted.most_common(1)[0][0] if counted else ""


def load_recipes() -> list[RecipeView]:
    """Une requête par table (pas de N+1) puis assemblage en mémoire."""
    ingredients = {
        i.id: i
        for i in Ingredient.objects.only(
            "allergens", "allergens_reviewed", "diet_flags", "aisle", "protein"
        )
    }
    lines = defaultdict(list)
    for recipe_id, ingredient_id, needs_review, raw in RecipeIngredient.objects.values_list(
        "recipe_id", "ingredient_id", "needs_review", "raw_text"
    ):
        lines[recipe_id].append((ingredient_id, needs_review, raw))
    equipment = defaultdict(set)
    for recipe_id, code, required in RecipeEquipment.objects.values_list(
        "recipe_id", "equipment_id", "required"
    ):
        if required:
            equipment[recipe_id].add(code)
    fields = [
        "id",
        "title",
        "meal_types",
        "servings",
        "prep_minutes",
        "cook_minutes",
        "cookeo_compatible",
        "tags",
        "cost_level",
    ]
    return [
        _view(recipe, lines[recipe.id], ingredients, equipment[recipe.id])
        for recipe in Recipe.objects.only(*fields)
    ]


def _view(recipe: Recipe, lines, ingredients, equipment) -> RecipeView:
    known = [ingredients.get(ingredient_id) for ingredient_id, _, _ in lines]
    sure = bool(lines) and all(
        ing is not None and not review for ing, (_, review, _) in zip(known, lines, strict=True)
    )
    minutes = [m for m in (recipe.prep_minutes, recipe.cook_minutes) if m is not None]
    present = [ing for ing in known if ing is not None]
    tags = frozenset(recipe.tags)
    style_texts = [recipe.title, *(raw for _, _, raw in lines)]
    cuisine = infer_cuisine(tags, style_texts)
    required = set(equipment) | ({Equipment.COOKEO.value} if recipe.cookeo_compatible else set())
    return RecipeView(
        id=str(recipe.id),
        title=recipe.title,
        meal_types=frozenset(recipe.meal_types),
        servings=recipe.servings,
        total_minutes=sum(minutes) if minutes else None,
        cookeo=recipe.cookeo_compatible,
        required_equipment=frozenset(required),
        allergens=frozenset(a for ing in present for a in ing.allergens),
        allergens_certain=sure and all(ing.allergens_reviewed for ing in present),
        diet_flags=frozenset(f for ing in present for f in ing.diet_flags),
        diet_certain=sure,
        ingredient_ids=frozenset(i for i, _, _ in lines if i is not None),
        perishable_ids=frozenset(ing.id for ing in present if is_perishable(ing.aisle)),
        produce_ids=frozenset(ing.id for ing in present if ing.aisle == Aisle.FRUITS_VEGETABLES),
        words=recipe_words([raw for _, _, raw in lines]),
        tags=tags,
        protein=_protein([ing.protein for ing in present]),
        cuisine=cuisine,
        spice=spice_level(tags, style_texts),
        exotic=is_exotic(cuisine),
        cost_level=recipe.cost_level,
    )


def load_learned_tastes(household) -> dict[int, float]:
    """Goûts déduits des notes du foyer ; les goûts saisis à la main les remplacent."""
    ratings = {
        str(recipe_id): rating
        for recipe_id, rating in RecipeFeedback.objects.for_household(household)
        .exclude(rating=None)
        .values_list("recipe_id", "rating")
    }
    if not ratings:
        return {}
    lines = defaultdict(set)
    for recipe_id, ingredient_id in RecipeIngredient.objects.filter(
        recipe_id__in=list(ratings), ingredient__isnull=False
    ).values_list("recipe_id", "ingredient_id"):
        lines[str(recipe_id)].add(ingredient_id)
    return learn_tastes(ratings, {k: frozenset(v) for k, v in lines.items()})


@dataclass(frozen=True)
class IngredientLookup:
    """Ingrédients du catalogue par allergène déclaré et par mots du nom (chargés une fois)."""

    by_allergen: Mapping[str, frozenset[int]]
    words: Mapping[int, frozenset[str]]

    def matching(self, coverage: restrictions.Coverage) -> set[int]:
        ids = {i for allergen in coverage.allergens for i in self.by_allergen.get(allergen, ())}
        ids |= {
            i for i, words in self.words.items() if any(ws <= words for ws in coverage.word_sets)
        }
        return ids


def load_ingredient_lookup() -> IngredientLookup:
    by_allergen = defaultdict(set)
    words = {}
    for ingredient_id, name, aliases, allergens in Ingredient.objects.values_list(
        "id", "name", "aliases", "allergens"
    ):
        words[ingredient_id] = restrictions.word_set(" ".join([name, *aliases]))
        for allergen in allergens:
            by_allergen[allergen].add(ingredient_id)
    return IngredientLookup({k: frozenset(v) for k, v in by_allergen.items()}, words)


def load_diners(household, diner_ids=None) -> list[DinerView]:
    queryset = Diner.objects.for_household(household).prefetch_related("restrictions", "tastes")
    if diner_ids is not None:
        queryset = queryset.filter(pk__in=diner_ids)
    lookup = load_ingredient_lookup()
    learned = load_learned_tastes(household)
    return [_diner_view(d, lookup, learned) for d in queryset]


def _diner_view(diner: Diner, lookup: IngredientLookup, learned) -> DinerView:
    explicit = {t.ingredient_id: t.score for t in diner.tastes.all()}
    strict, words, taste = set(), set(), {**learned, **explicit}
    for restriction in diner.restrictions.all():
        covered = restriction.coverage
        if restriction.severity == STRICT:
            strict |= covered.allergens
            words |= covered.word_sets
        else:
            taste.update({i: AVOID_SCORE for i in lookup.matching(covered)})
    return DinerView(
        id=str(diner.pk),
        name=diner.first_name,
        strict_allergens=frozenset(strict),
        strict_word_sets=frozenset(words),
        diets=frozenset(diner.diets),
        taste=taste,
    )


def load_history(household, exclude_plan=None, today: date | None = None) -> History:
    today = today or date.today()  # noqa: DTZ011 - date locale du foyer
    served: dict[str, date] = {}
    feedback = RecipeFeedback.objects.for_household(household)
    for recipe_id, last in feedback.exclude(last_served_on=None).values_list(
        "recipe_id", "last_served_on"
    ):
        served[str(recipe_id)] = last
    slots = MenuSlot.objects.for_household(household).filter(
        recipe__isnull=False, day__gte=today - timedelta(days=HISTORY_DAYS), leftover=False
    )
    if exclude_plan is not None:
        slots = slots.exclude(plan=exclude_plan)
    for recipe_id, day in slots.values_list("recipe_id", "day"):
        key = str(recipe_id)
        served[key] = max(day, served.get(key, day))
    return History(
        last_served=served,
        excluded=frozenset(
            str(i) for i in feedback.filter(excluded=True).values_list("recipe_id", flat=True)
        ),
        favorites=frozenset(
            str(i) for i in feedback.filter(favorite=True).values_list("recipe_id", flat=True)
        ),
        ratings={
            str(i): r for i, r in feedback.exclude(rating=None).values_list("recipe_id", "rating")
        },
    )


def build_context(
    household, settings: HouseholdSettings, diners, history, today, **extra
) -> Context:
    names = dict(Ingredient.objects.values_list("id", "name"))
    seasonal = {i for i, n in names.items() if n in seasonal_names(today.month)}
    owned = frozenset(
        HouseholdEquipment.objects.for_household(household).values_list("equipment_id", flat=True)
    )
    engine_settings = EngineSettings(
        equipment=owned,
        max_minutes_weekday=settings.max_minutes_weekday,
        max_minutes_weekend=settings.max_minutes_weekend,
        min_repeat_days=settings.min_repeat_days,
        budget_level=settings.budget_level,
        vegetarian_per_week=settings.vegetarian_per_week,
        weights=settings.weights or {},
        wanted_tags=frozenset(extra.get("wanted_tags", ())),
        allow_cookeo_split=bool(extra.get("allow_cookeo_split", False)),
        liked_cuisines=frozenset(settings.liked_cuisines),
        avoided_cuisines=frozenset(settings.avoided_cuisines),
        spice_tolerance=settings.spice_tolerance,
        exoticism=settings.exoticism,
        cuisine_labels={c.value: str(c.label) for c in Cuisine},
    )
    return Context(
        diners={d.id: d for d in diners},
        settings=engine_settings,
        history=history,
        today=today,
        in_season_ids=frozenset(seasonal),
        ingredient_names=names,
    )
