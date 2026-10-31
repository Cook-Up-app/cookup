from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from apps.catalog.models import Ingredient, Recipe
from apps.core.reference import Allergen
from apps.households.models import (
    Diner,
    DinerRestriction,
    HouseholdEquipment,
    HouseholdSettings,
    Membership,
    TastePreference,
)
from apps.planner import loading, services
from apps.planner.models import MenuPlan, MenuSlot
from tests.conftest import make_user, seed_catalog

TODAY = timezone.localdate()


@pytest.fixture
def ready(owner_client, owner, db):
    seed_catalog()
    household = Membership.objects.get(user=owner).household
    for code in ("hob", "oven", "blender", "food_processor", "microwave"):
        HouseholdEquipment.objects.create(household=household, equipment_id=code)
    Diner.objects.create(household=household, first_name="Léa")
    return owner_client, household


def form_data(household, **overrides):
    data = {
        "start_date": TODAY.isoformat(),
        "days": 3,
        "meals": ["lunch", "dinner"],
        "diners": [str(d.pk) for d in household.diners.all()],
        "guests": 0,
        "mode": "classic",
        "cookeo_share": 50,
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize("name", ["planner:list", "planner:new"])
def test_menu_pages_require_a_session(client, db, name):
    assert client.get(reverse(name)).status_code == 302


def test_generation_creates_a_plan(ready):
    client, household = ready

    response = client.post(reverse("planner:generate"), form_data(household))

    plan = MenuPlan.objects.get()
    assert response.status_code == 302 and response["Location"] == reverse(
        "planner:detail", args=[plan.pk]
    )
    assert plan.slots.count() == 6 and plan.household == household


def test_new_menu_form_is_prefilled_from_settings(ready):
    client, _ = ready

    page = client.get(reverse("planner:new")).content.decode()

    assert TODAY.isoformat() in page and "garantie médicale" in page


def test_detail_shows_explanations_and_actions(ready):
    client, household = ready
    client.post(reverse("planner:generate"), form_data(household))
    plan = MenuPlan.objects.get()

    page = client.get(reverse("planner:detail", args=[plan.pk])).content.decode()

    assert "Verrouiller" in page and "Remplacer" in page and "Hors maison" in page
    assert escape(plan.slots.first().recipe.title) in page  # le HTML échappe apostrophes et \&


def test_simple_member_without_mfa_can_plan_menus(client, ready):
    _, household = ready
    member = make_user("member@example.com", mfa=False)
    Membership.objects.create(user=member, household=household)
    client.force_login(member)

    response = client.post(reverse("planner:generate"), form_data(household))

    assert response.status_code == 302 and MenuPlan.objects.count() == 1


def test_impossible_menu_explains_what_blocks(ready):
    client, household = ready
    diner = household.diners.get()
    for allergen in (Allergen.GLUTEN, Allergen.MILK, Allergen.EGGS):
        DinerRestriction.objects.create(diner=diner, allergen=allergen)

    response = client.post(reverse("planner:generate"), form_data(household, quick="on"))

    assert response.status_code == 200 and not MenuPlan.objects.exists()
    page = response.content.decode()
    assert "% sont écartées" in page or "% des recettes sont écartées" in page


def test_foreign_diners_are_rejected_by_the_form(ready, other_owner):
    client, household = ready
    foreign = Diner.objects.create(
        household=Membership.objects.get(user=other_owner).household, first_name="X"
    )

    response = client.post(
        reverse("planner:generate"), form_data(household, diners=[str(foreign.pk)])
    )

    assert response.status_code == 200 and not MenuPlan.objects.exists()


def test_cookeo_mode_is_unusable_without_the_equipment(ready):
    client, household = ready

    response = client.post(reverse("planner:generate"), form_data(household, mode="cookeo"))

    assert (
        response.status_code == 200
        and "exige l&#x27;équipement Cookeo" in response.content.decode()
    )
    assert not MenuPlan.objects.exists()


def test_lock_and_regenerate_keep_locked_meals(ready):
    client, household = ready
    client.post(reverse("planner:generate"), form_data(household))
    plan = MenuPlan.objects.get()
    slot = plan.slots.order_by("day", "meal_type").first()
    kept = slot.recipe_id

    client.post(reverse("planner:lock", args=[plan.pk, slot.pk]))
    client.post(reverse("planner:regenerate", args=[plan.pk]))

    slot.refresh_from_db()
    assert slot.locked and slot.recipe_id == kept


def test_replace_offers_three_alternatives_then_applies_a_valid_one(ready):
    client, household = ready
    client.post(reverse("planner:generate"), form_data(household))
    plan = MenuPlan.objects.get()
    slot = plan.slots.first()
    url = reverse("planner:replace", args=[plan.pk, slot.pk])

    page = client.post(url).content.decode()
    options = services.alternatives_for(slot, TODAY)
    client.post(url, {"recipe": str(options[0].pk)})

    assert page.count('name="recipe"') == 3
    slot.refresh_from_db()
    assert slot.recipe_id == options[0].pk


def test_replace_refuses_a_forbidden_recipe(ready):
    client, household = ready
    DinerRestriction.objects.create(diner=household.diners.get(), allergen=Allergen.MILK)
    client.post(reverse("planner:generate"), form_data(household))
    plan = MenuPlan.objects.get()
    slot = plan.slots.first()
    before = slot.recipe_id
    forbidden = Recipe.objects.filter(ingredients__ingredient__allergens__contains=["milk"]).first()

    response = client.post(
        reverse("planner:replace", args=[plan.pk, slot.pk]), {"recipe": str(forbidden.pk)}
    )
    garbage = client.post(
        reverse("planner:replace", args=[plan.pk, slot.pk]), {"recipe": "pas-un-uuid"}
    )

    assert response.status_code == 404 and garbage.status_code == 404
    slot.refresh_from_db()
    assert slot.recipe_id == before


def test_out_of_home_toggle(ready):
    client, household = ready
    client.post(reverse("planner:generate"), form_data(household))
    plan = MenuPlan.objects.get()
    slot = plan.slots.first()

    client.post(reverse("planner:out-of-home", args=[plan.pk, slot.pk]))

    slot.refresh_from_db()
    assert slot.out_of_home and slot.recipe_id is None


@pytest.fixture
def foreign_plan(ready, other_owner, client):
    """Menu du foyer B, que le propriétaire du foyer A ne doit pas atteindre."""
    other = Membership.objects.get(user=other_owner).household
    HouseholdEquipment.objects.create(household=other, equipment_id="hob")
    plan = services.create_plan(
        other,
        services.PlanRequest(
            start_date=TODAY, end_date=TODAY, meals=("lunch",), diner_ids=(), mode="classic"
        ),
        TODAY,
        seed=1,
    )
    return plan, plan.slots.get()


@pytest.mark.parametrize("name", ["planner:detail", "planner:regenerate"])
def test_foreign_plan_is_not_found(ready, foreign_plan, name):
    client, _ = ready
    plan, _ = foreign_plan

    assert client.get(reverse(name, args=[plan.pk])).status_code in (404, 405)
    assert client.post(reverse(name, args=[plan.pk])).status_code in (404, 405)


@pytest.mark.parametrize("name", ["planner:lock", "planner:replace", "planner:out-of-home"])
def test_foreign_slots_are_not_found_even_through_my_own_plan(ready, foreign_plan, name):
    client, household = ready
    client.post(reverse("planner:generate"), form_data(household))
    mine = MenuPlan.objects.get(household=household)
    plan, slot = foreign_plan

    assert client.post(reverse(name, args=[plan.pk, slot.pk])).status_code == 404
    assert client.post(reverse(name, args=[mine.pk, slot.pk])).status_code == 404
    slot.refresh_from_db()
    assert not slot.locked and slot.recipe_id is not None


def test_lists_do_not_leak_foreign_plans(ready, foreign_plan):
    client, _ = ready

    assert foreign_plan[0].start_date.strftime("%d/%m/%Y") in str(TODAY.strftime("%d/%m/%Y"))
    assert MenuPlan.objects.count() == 1
    assert "Aucun menu" in client.get(reverse("planner:list")).content.decode()


@pytest.mark.parametrize("name", ["planner:regenerate", "planner:generate"])
def test_post_only_endpoints_reject_get(ready, name):
    client, _ = ready
    args = (
        [MenuPlan.objects.create(household=ready[1], start_date=TODAY, end_date=TODAY, seed=1).pk]
        if "regen" in name
        else []
    )

    assert client.get(reverse(name, args=args)).status_code == 405


def test_pages_stay_within_the_query_budget(ready, django_assert_max_num_queries):
    client, household = ready
    client.post(reverse("planner:generate"), form_data(household, days=7))
    plan = MenuPlan.objects.get()

    with django_assert_max_num_queries(15):
        assert client.get(reverse("planner:detail", args=[plan.pk])).status_code == 200
    with django_assert_max_num_queries(15):
        assert client.get(reverse("planner:list")).status_code == 200


def test_owner_sets_preferences_and_weights(ready):
    client, household = ready
    data = {
        "meals": ["lunch", "dinner"],
        "max_minutes_weekday": 30,
        "max_minutes_weekend": 90,
        "budget_level": 1,
        "leftover_weekdays": ["1"],
        "min_repeat_days": 10,
        "vegetarian_per_week": 3,
        "source_mode": "classic",
        "cookeo_share": 50,
        "weight_taste": 50,
    }

    client.post(reverse("households:preferences"), data)

    settings = HouseholdSettings.objects.get(household=household)
    assert (settings.max_minutes_weekday, settings.leftover_weekdays, settings.weights) == (
        30,
        [1],
        {"taste": 50},
    )


def test_out_of_range_weight_is_rejected(ready):
    client, household = ready

    response = client.post(
        reverse("households:preferences"),
        {
            "meals": ["lunch"],
            "max_minutes_weekday": 30,
            "max_minutes_weekend": 60,
            "budget_level": 2,
            "min_repeat_days": 7,
            "vegetarian_per_week": 2,
            "source_mode": "classic",
            "cookeo_share": 50,
            "weight_taste": 500,
        },
    )

    assert (
        response.status_code == 200
        and not HouseholdSettings.objects.filter(household=household).exclude(weights={}).exists()
    )


def test_tastes_are_saved_and_reach_the_engine(ready):
    client, household = ready
    diner = household.diners.get()
    chicken = Ingredient.objects.get(name="poulet")
    carrot = Ingredient.objects.get(name="carotte")

    client.post(
        reverse("households:diner-tastes", args=[diner.pk]),
        {"likes": [chicken.pk], "dislikes": [carrot.pk]},
    )

    assert dict(TastePreference.objects.values_list("ingredient_id", "score")) == {
        chicken.pk: 2,
        carrot.pk: -2,
    }
    view = loading.load_diners(household)[0]
    assert view.taste[chicken.pk] == 2 and view.taste[carrot.pk] == -2


def test_item_cannot_be_liked_and_disliked(ready):
    client, household = ready
    diner = household.diners.get()
    chicken = Ingredient.objects.get(name="poulet")

    client.post(
        reverse("households:diner-tastes", args=[diner.pk]),
        {"likes": [chicken.pk], "dislikes": [chicken.pk]},
    )

    assert not TastePreference.objects.exists()


def test_intolerance_lowers_the_taste_score_without_excluding(ready):
    _, household = ready
    diner = household.diners.get()
    DinerRestriction.objects.create(diner=diner, allergen=Allergen.MILK, severity="intolerance")

    view = loading.load_diners(household)[0]
    milk = Ingredient.objects.get(name="lait")

    assert view.taste[milk.pk] == -2 and not view.strict_allergens


def test_taste_page_of_another_household_is_not_found(ready, other_owner):
    client, _ = ready
    foreign = Diner.objects.create(
        household=Membership.objects.get(user=other_owner).household, first_name="X"
    )

    assert client.get(reverse("households:diner-tastes", args=[foreign.pk])).status_code == 404


def test_history_marks_recently_planned_recipes(ready):
    client, household = ready
    client.post(reverse("planner:generate"), form_data(household))
    plan = MenuPlan.objects.get()

    history = loading.load_history(household, today=TODAY)

    assert {str(s.recipe_id) for s in plan.slots.all()} <= set(history.last_served)
    assert not loading.load_history(household, exclude_plan=plan, today=TODAY).last_served
    assert MenuSlot.objects.count() == 6 and timedelta(days=0) == timedelta()
