"""Génération complète contre la base, avec le catalogue de départ."""

from datetime import date, timedelta

import pytest

from apps.catalog.models import Recipe, RecipeFeedback
from apps.catalog.services import recipe_allergens
from apps.core.reference import Allergen
from apps.households import services as household_services
from apps.households.models import (
    Diner,
    DinerRestriction,
    Equipment,
    HouseholdEquipment,
    HouseholdSettings,
    Membership,
)
from apps.planner import services
from apps.planner.engine import NotEnoughCandidates
from apps.planner.models import MenuPlan
from tests.conftest import make_user, seed_catalog

TODAY = date(2026, 11, 2)


@pytest.fixture
def home(db):
    seed_catalog()
    user = make_user("boss@example.com")
    household_services.create_household(user, "Foyer")
    household = Membership.objects.get().household
    for code in ("hob", "oven", "blender", "food_processor", "microwave"):
        HouseholdEquipment.objects.create(household=household, equipment_id=code)
    return household


def request(household, **overrides) -> services.PlanRequest:
    diners = overrides.pop("diner_ids", tuple(str(d.pk) for d in household.diners.all()))
    values = {
        "start_date": TODAY,
        "end_date": TODAY + timedelta(days=6),
        "meals": ("lunch", "dinner"),
        "diner_ids": diners,
    }
    values.update(overrides)
    return services.PlanRequest(**values)


def recipes_of(plan: MenuPlan) -> list[Recipe]:
    return [s.recipe for s in plan.slots.select_related("recipe") if s.recipe]


def test_a_week_is_generated_and_saved(home):
    Diner.objects.create(household=home, first_name="Léa")

    plan = services.create_plan(home, request(home), TODAY, seed=1)

    assert plan.slots.count() == 14
    assert all(s.recipe_id and s.explanation for s in plan.slots.all())
    assert len({s.recipe_id for s in plan.slots.all()}) == 14


def test_same_seed_and_data_give_the_same_menu(home):
    Diner.objects.create(household=home, first_name="Léa")
    first = services.create_plan(home, request(home), TODAY, seed=42)
    chosen = [s.recipe_id for s in first.slots.all()]
    first.delete()  # sinon ce premier menu entrerait dans l'historique du second

    second = services.create_plan(home, request(home), TODAY, seed=42)

    assert [s.recipe_id for s in second.slots.all()] == chosen


@pytest.mark.parametrize(
    "allergen", [Allergen.TREE_NUTS, Allergen.MILK, Allergen.EGGS, Allergen.GLUTEN]
)
def test_strict_allergies_are_never_served(home, allergen):
    diner = Diner.objects.create(household=home, first_name="Léa")
    DinerRestriction.objects.create(diner=diner, allergen=allergen)

    for seed in range(15):
        try:
            plan = services.create_plan(
                home, request(home, end_date=TODAY + timedelta(days=2)), TODAY, seed=seed
            )
        except NotEnoughCandidates:
            continue
        for recipe in Recipe.objects.filter(
            pk__in=[r.pk for r in recipes_of(plan)]
        ).prefetch_related("ingredients__ingredient"):
            allergens, uncertain = recipe_allergens(recipe)
            assert allergen not in allergens and not uncertain, recipe.title


def test_unconfirmed_ingredients_are_refused_when_an_allergy_exists(home):
    diner = Diner.objects.create(household=home, first_name="Léa")
    DinerRestriction.objects.create(diner=diner, allergen=Allergen.PEANUTS)

    plan = services.create_plan(home, request(home), TODAY, seed=3)

    for recipe in Recipe.objects.filter(pk__in=[r.pk for r in recipes_of(plan)]):
        assert not recipe.needs_review
        assert not recipe.ingredients.filter(ingredient__allergens_reviewed=False).exists()


def test_vegetarian_diner_gets_no_meat_or_fish(home):
    Diner.objects.create(household=home, first_name="Léa", diets=["vegetarian"])

    plan = services.create_plan(
        home, request(home, end_date=TODAY + timedelta(days=3)), TODAY, seed=5
    )

    for recipe in recipes_of(plan):
        flags = {
            f
            for line in recipe.ingredients.select_related("ingredient")
            for f in line.ingredient.diet_flags
        }
        assert not flags & {"meat", "fish"}, recipe.title


def test_cookeo_mode_needs_cookeo_equipment_and_only_uses_cookeo_recipes(home):
    Diner.objects.create(household=home, first_name="Léa")
    request_ = request(home, mode="cookeo", end_date=TODAY + timedelta(days=3))
    with pytest.raises(NotEnoughCandidates):
        services.create_plan(home, request_, TODAY, seed=1)

    HouseholdEquipment.objects.create(household=home, equipment_id="cookeo_yy5449fb")
    plan = services.create_plan(home, request_, TODAY, seed=1)

    assert all(r.cookeo_compatible for r in recipes_of(plan))


def test_mixed_mode_blends_both_sources(home):
    HouseholdEquipment.objects.create(household=home, equipment_id="cookeo_yy5449fb")
    Diner.objects.create(household=home, first_name="Léa")

    plan = services.create_plan(home, request(home, mode="mixed", cookeo_share=50), TODAY, seed=2)

    cookeo = [r.cookeo_compatible for r in recipes_of(plan)]
    assert 0 < sum(cookeo) < len(cookeo)


def test_servings_follow_diners_and_guests(home):
    Diner.objects.create(household=home, first_name="Léa")
    Diner.objects.create(household=home, first_name="Tom")

    plan = services.create_plan(home, request(home, guests=2), TODAY, seed=1)

    assert {s.servings for s in plan.slots.all()} == {4}


def test_regeneration_keeps_locked_slots_and_changes_the_rest(home):
    Diner.objects.create(household=home, first_name="Léa")
    plan = services.create_plan(home, request(home), TODAY, seed=1)
    locked = plan.slots.order_by("day", "meal_type").first()
    services.toggle_lock(locked)
    before = {s.pk: s.recipe_id for s in plan.slots.all()}

    services.regenerate_plan(plan, TODAY)

    after = {s.pk: s.recipe_id for s in plan.slots.all()}
    assert after[locked.pk] == before[locked.pk]
    assert sum(after[k] != before[k] for k in before) >= 8
    assert len(set(after.values())) == 14


def test_replace_applies_only_allowed_recipes(home):
    diner = Diner.objects.create(household=home, first_name="Léa")
    DinerRestriction.objects.create(diner=diner, allergen=Allergen.MILK)
    plan = services.create_plan(home, request(home), TODAY, seed=1)
    slot = plan.slots.first()
    forbidden = Recipe.objects.filter(ingredients__ingredient__allergens__contains=["milk"]).first()

    with pytest.raises(services.ReplacementRefused):
        services.replace_slot(slot, str(forbidden.pk), TODAY)

    options = services.alternatives_for(slot, TODAY)
    assert len(options) == 3
    services.replace_slot(slot, str(options[0].pk), TODAY)
    slot.refresh_from_db()
    assert slot.recipe_id == options[0].pk


def test_out_of_home_slots_get_no_recipe(home):
    Diner.objects.create(household=home, first_name="Léa")
    out = f"{TODAY.isoformat()}:dinner"

    plan = services.create_plan(home, request(home, out_of_home=(out,)), TODAY, seed=1)

    slot = plan.slots.get(day=TODAY, meal_type="dinner")
    assert slot.out_of_home and slot.recipe_id is None
    assert plan.slots.count() == 14


def test_toggle_out_of_home_clears_the_recipe(home):
    Diner.objects.create(household=home, first_name="Léa")
    plan = services.create_plan(home, request(home), TODAY, seed=1)
    slot = plan.slots.first()

    services.toggle_out_of_home(slot)

    assert slot.recipe_id is None and slot.out_of_home and not slot.locked


def test_recent_and_excluded_recipes_are_avoided(home):
    Diner.objects.create(household=home, first_name="Léa")
    first = services.create_plan(
        home, request(home, end_date=TODAY + timedelta(days=1)), TODAY, seed=1
    )
    served = {s.recipe_id for s in first.slots.all()}
    excluded = Recipe.objects.exclude(pk__in=served).first()
    RecipeFeedback.objects.create(household=home, recipe=excluded, excluded=True)

    second = services.create_plan(
        home, request(home, end_date=TODAY + timedelta(days=1)), TODAY + timedelta(days=1), seed=2
    )

    chosen = {s.recipe_id for s in second.slots.all()}
    assert not chosen & served and excluded.pk not in chosen


def test_leftover_day_reuses_the_previous_dinner(home):
    Diner.objects.create(household=home, first_name="Léa")
    settings = HouseholdSettings.objects.create(household=home, leftover_weekdays=[1])

    plan = services.create_plan(
        home, request(home, end_date=TODAY + timedelta(days=2)), TODAY, seed=4
    )

    tuesday_lunch = plan.slots.get(day=TODAY + timedelta(days=1), meal_type="lunch")
    monday_dinner = plan.slots.get(day=TODAY, meal_type="dinner")
    assert settings.leftover_weekdays == [1]
    assert tuesday_lunch.leftover and tuesday_lunch.recipe_id == monday_dinner.recipe_id


def test_failure_message_lists_the_blocking_constraints(home):
    diner = Diner.objects.create(household=home, first_name="Léa")
    for allergen in (Allergen.GLUTEN, Allergen.MILK, Allergen.EGGS):
        DinerRestriction.objects.create(diner=diner, allergen=allergen)
    from apps.planner.messages import describe_failure

    with pytest.raises(NotEnoughCandidates) as caught:
        services.create_plan(home, request(home, quick=True), TODAY, seed=1)

    message = describe_failure(caught.value.report)
    assert "%" in message and "allergies" in message


def test_request_round_trips_through_json(home):
    original = request(home, mode="mixed", wanted_tags=("soupe",), without_equipment=("oven",))

    assert services.PlanRequest.from_params(original.to_params()) == original


def test_equipment_codes_come_from_the_catalogue(home):
    assert set(Equipment.objects.values_list("code", flat=True)) >= {
        "oven",
        "hob",
        "cookeo_yy5449fb",
    }
