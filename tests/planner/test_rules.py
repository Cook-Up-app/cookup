from datetime import timedelta

import pytest

from apps.planner.engine import History, Violation, is_allowed, violations
from tests.planner.builders import MONDAY, context, diner, recipe, slots

SLOT = slots(1, meals=("lunch",))[0]


def found(recipe_, ctx=None, slot=SLOT):
    return violations(recipe_, slot, ctx or context())


def test_a_plain_recipe_is_allowed():
    assert found(recipe()) == []


def test_strict_allergen_is_excluded():
    ctx = context([diner(strict_allergens=frozenset({"tree_nuts"}))])

    assert found(recipe(allergens=frozenset({"tree_nuts", "milk"})), ctx) == [Violation.ALLERGEN]
    assert found(recipe(allergens=frozenset({"milk"})), ctx) == []


def test_allergy_of_any_present_diner_counts_but_absent_ones_do_not():
    ctx = context([diner("Léa"), diner("Tom", strict_allergens=frozenset({"eggs"}))])
    eggs = recipe(allergens=frozenset({"eggs"}))

    assert found(eggs, ctx, slots(1, ("lunch",), diner_ids=("léa", "tom"))[0]) == [
        Violation.ALLERGEN
    ]
    assert found(eggs, ctx, slots(1, ("lunch",), diner_ids=("léa",))[0]) == []


def test_unknown_ingredient_is_refused_only_when_an_allergy_exists():
    unsure = recipe(allergens_certain=False)

    assert found(unsure) == []
    ctx = context([diner(strict_allergens=frozenset({"eggs"}))])
    assert found(unsure, ctx) == [Violation.UNCERTAIN_ALLERGENS]


def test_free_text_strict_restriction_matches_ingredient_words():
    ctx = context([diner(strict_word_sets=frozenset({frozenset({"kiwi"})}))])

    assert found(recipe(words=frozenset({"salade", "kiwi"})), ctx) == [Violation.ALLERGEN]
    assert found(recipe(words=frozenset({"salade"})), ctx) == []


@pytest.mark.parametrize(
    ("diet", "flags", "blocked"),
    [
        ("vegetarian", {"meat"}, True),
        ("vegetarian", {"fish"}, True),
        ("vegetarian", {"animal"}, False),
        ("vegan", {"animal"}, True),
        ("pescatarian", {"fish"}, False),
        ("pescatarian", {"meat"}, True),
        ("no_pork", {"pork"}, True),
        ("no_pork", {"meat"}, False),
        ("halal", {"pork"}, True),
        ("halal", {"alcohol"}, True),
        ("halal", {"meat"}, False),
        ("kosher", {"pork"}, True),
    ],
)
def test_diets(diet, flags, blocked):
    ctx = context([diner(diets=frozenset({diet}))])

    result = found(recipe(diet_flags=frozenset(flags)), ctx)

    assert (result == [Violation.DIET]) is blocked


def test_kosher_forbids_shellfish_and_meat_with_dairy():
    ctx = context([diner(diets=frozenset({"kosher"}))])

    assert found(recipe(allergens=frozenset({"crustaceans"})), ctx) == [Violation.DIET]
    assert found(recipe(diet_flags=frozenset({"meat"}), allergens=frozenset({"milk"})), ctx) == [
        Violation.DIET
    ]


def test_diet_with_unknown_ingredient_fails_safe():
    ctx = context([diner(diets=frozenset({"vegan"}))])

    assert found(recipe(diet_certain=False), ctx) == [Violation.UNCERTAIN_DIET]


def test_equipment_must_be_owned_and_allowed_for_the_slot():
    oven_recipe = recipe(required_equipment=frozenset({"oven"}))
    air_fryer = recipe(required_equipment=frozenset({"air_fryer"}))

    assert found(oven_recipe) == []
    assert found(air_fryer) == [Violation.EQUIPMENT]
    no_oven = slots(1, ("lunch",), forbidden_equipment=frozenset({"oven"}))[0]
    assert found(oven_recipe, slot=no_oven) == [Violation.EQUIPMENT]


def test_source_mode():
    classic, cookeo = recipe(), recipe(cookeo=True, required_equipment=frozenset({"cookeo"}))
    ctx = context(equipment=frozenset({"cookeo"}))
    cookeo_slot = slots(1, ("lunch",), mode="cookeo")[0]
    classic_slot = slots(1, ("lunch",), mode="classic")[0]

    assert found(classic, ctx, cookeo_slot) == [Violation.SOURCE]
    assert found(cookeo, ctx, cookeo_slot) == []
    assert found(cookeo, ctx, classic_slot) == [Violation.SOURCE]


def test_time_limits_differ_between_weekdays_and_weekends():
    long_recipe = recipe(total_minutes=60)
    weekday, saturday = (
        slots(1, ("lunch",))[0],
        slots(1, ("lunch",), start=MONDAY + timedelta(days=5))[0],
    )

    assert found(long_recipe, slot=weekday) == [Violation.TIME]  # 45 min en semaine
    assert found(long_recipe, slot=saturday) == []  # 90 min le week-end
    assert found(recipe(total_minutes=None), slot=weekday) == []  # durée inconnue : permise
    quick = slots(1, ("lunch",), max_minutes=20)[0]
    assert found(recipe(total_minutes=25), slot=quick) == [Violation.TIME]


def test_meal_type_must_match():
    assert found(recipe(meal_types=frozenset({"dessert"}))) == [Violation.MEAL_TYPE]


def test_cookeo_capacity_is_six_servings():
    cookeo = recipe(cookeo=True, required_equipment=frozenset({"cookeo"}))
    ctx = context(equipment=frozenset({"cookeo"}))
    big = slots(1, ("lunch",), diner_ids=("léa",), mode="cookeo", extra_cook_servings=6)[0]

    assert found(cookeo, ctx, big) == [Violation.PORTIONS]


def test_excluded_and_recently_served_recipes():
    excluded, recent = recipe(), recipe()
    history = History(
        excluded=frozenset({excluded.id}), last_served={recent.id: MONDAY - timedelta(days=5)}
    )
    ctx = context(history=history)

    assert found(excluded, ctx) == [Violation.EXCLUDED]
    assert found(recent, ctx) == [Violation.RECENT]
    old = recipe()
    ctx_old = context(history=History(last_served={old.id: MONDAY - timedelta(days=30)}))
    assert is_allowed(old, SLOT, ctx_old)


def test_violations_accumulate():
    ctx = context([diner(strict_allergens=frozenset({"eggs"}))])

    result = found(
        recipe(allergens=frozenset({"eggs"}), total_minutes=120, meal_types=frozenset({"snack"})),
        ctx,
    )

    assert set(result) == {Violation.ALLERGEN, Violation.TIME, Violation.MEAL_TYPE}
