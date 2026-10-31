"""Mode Cookeo (jalon M5) : capacité de la cuve, mode mixte, équipement obligatoire."""

import re
from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Recipe
from apps.core.reference import Equipment
from apps.households.models import (
    Diner,
    HouseholdEquipment,
    HouseholdSettings,
    Membership,
)
from apps.planner import services
from apps.planner.engine import NotEnoughCandidates, Violation, assign_modes, generate, violations
from apps.planner.models import MenuPlan
from tests.conftest import seed_catalog
from tests.planner.builders import context, recipe, slots

TODAY = timezone.localdate()
COOKEO = Equipment.COOKEO.value


def cookeo_recipe(**overrides):
    return recipe(cookeo=True, required_equipment=frozenset({COOKEO}), **overrides)


def cookeo_ctx(**overrides):
    return context(equipment=frozenset({COOKEO, "hob"}), **overrides)


def test_over_six_servings_is_refused_without_the_split_option():
    eight = slots(1, ("lunch",), diner_ids=("léa",), mode="cookeo", extra_cook_servings=7)[0]

    assert violations(cookeo_recipe(), eight, cookeo_ctx()) == [Violation.PORTIONS]


def test_splitting_allows_more_than_six_servings_and_says_so():
    eight = slots(1, ("lunch",), diner_ids=("léa",), mode="cookeo", extra_cook_servings=7)
    ctx = cookeo_ctx(allow_cookeo_split=True)

    plan = generate(eight, [cookeo_recipe()], ctx, seed=1)

    assert violations(cookeo_recipe(), eight[0], ctx) == []
    assert "à cuire en 2 fois" in plan.assignments[0].explanation


def test_six_servings_or_fewer_need_no_split():
    six = slots(1, ("lunch",), diner_ids=("léa",), mode="cookeo", extra_cook_servings=5)[0]

    assert violations(cookeo_recipe(), six, cookeo_ctx()) == []


def test_cookeo_slots_never_get_classic_recipes_and_the_reverse():
    ctx = cookeo_ctx()
    week = assign_modes(slots(2), "mixed", 50, seed=3)
    pool = [cookeo_recipe() for _ in range(8)] + [recipe() for _ in range(8)]

    plan = generate(week, pool, ctx, seed=3)

    by_id = {r.id: r for r in pool}
    for slot, assignment in zip(week, plan.assignments, strict=True):
        assert by_id[assignment.recipe_id].cookeo == (slot.mode == "cookeo")


def test_one_cookeo_main_per_slot():
    week = assign_modes(slots(3), "cookeo", 100, seed=1)
    plan = generate(week, [cookeo_recipe() for _ in range(10)], cookeo_ctx(), seed=1)

    assert len({a.slot_key for a in plan.assignments}) == len(plan.assignments)


def test_not_enough_cookeo_recipes_is_reported_not_hidden():
    week = assign_modes(slots(3), "cookeo", 100, seed=1)

    with pytest.raises(NotEnoughCandidates) as caught:
        generate(week, [cookeo_recipe(), recipe()], cookeo_ctx(), seed=1)

    assert Violation.SOURCE in caught.value.report.top_reasons(2)


@pytest.fixture
def home(owner, db):
    seed_catalog()
    household = Membership.objects.get(user=owner).household
    for code in ("hob", "oven"):
        HouseholdEquipment.objects.create(household=household, equipment_id=code)
    return household


def request(home, **overrides):
    values = {
        "start_date": date(2026, 11, 2),
        "end_date": date(2026, 11, 4),
        "meals": ("lunch", "dinner"),
        "diner_ids": tuple(str(d.pk) for d in home.diners.all()),
    }
    values.update(overrides)
    return services.PlanRequest(**values)


def test_service_refuses_cookeo_modes_without_the_equipment(home):
    Diner.objects.create(household=home, first_name="Léa")

    for mode in ("cookeo", "mixed"):
        with pytest.raises(services.CookeoUnavailable):
            services.create_plan(home, request(home, mode=mode), date(2026, 11, 2), seed=1)
    assert not MenuPlan.objects.exists()


def test_cookeo_menu_only_has_compatible_recipes_that_need_the_equipment(home):
    HouseholdEquipment.objects.create(household=home, equipment_id=COOKEO)
    Diner.objects.create(household=home, first_name="Léa")

    plan = services.create_plan(home, request(home, mode="cookeo"), date(2026, 11, 2), seed=1)

    recipes = [s.recipe for s in plan.slots.select_related("recipe")]
    assert recipes and all(r.cookeo_compatible and r.cookeo_program for r in recipes)
    assert all(r.equipment.filter(equipment_id=COOKEO).exists() for r in recipes)


def test_mixed_mode_follows_the_requested_share(home):
    HouseholdEquipment.objects.create(household=home, equipment_id=COOKEO)
    Diner.objects.create(household=home, first_name="Léa")

    plan = services.create_plan(
        home, request(home, mode="mixed", cookeo_share=50), date(2026, 11, 2), seed=4
    )

    flags = [s.recipe.cookeo_compatible for s in plan.slots.select_related("recipe")]
    assert sum(flags) == 3 and len(flags) == 6


def test_a_large_table_in_cookeo_mode_needs_the_split_option(home):
    HouseholdEquipment.objects.create(household=home, equipment_id=COOKEO)
    for name in range(8):
        Diner.objects.create(household=home, first_name=f"D{name}")

    with pytest.raises(NotEnoughCandidates):
        services.create_plan(home, request(home, mode="cookeo"), date(2026, 11, 2), seed=1)
    plan = services.create_plan(
        home, request(home, mode="cookeo", split_cookeo=True), date(2026, 11, 2), seed=1
    )

    assert any("fois" in s.explanation for s in plan.slots.all())


def form_post(home, **overrides):
    data = {
        "start_date": TODAY.isoformat(),
        "days": 2,
        "meals": ["lunch", "dinner"],
        "diners": [str(d.pk) for d in home.diners.all()],
        "guests": 0,
        "mode": "cookeo",
        "cookeo_share": 50,
    }
    data.update(overrides)
    return data


def test_form_warns_and_proposes_splitting_above_six_people(owner_client, home):
    HouseholdEquipment.objects.create(household=home, equipment_id=COOKEO)
    for name in range(4):
        Diner.objects.create(household=home, first_name=f"D{name}")

    page = owner_client.post(
        reverse("planner:generate"), form_post(home, guests=3)
    ).content.decode()

    assert "6 portions au maximum" in page and "Scinder la cuisson Cookeo" in page
    assert not MenuPlan.objects.exists()


def test_form_accepts_more_than_six_with_the_split_option(owner_client, home):
    HouseholdEquipment.objects.create(household=home, equipment_id=COOKEO)
    for name in range(4):
        Diner.objects.create(household=home, first_name=f"D{name}")

    response = owner_client.post(
        reverse("planner:generate"), form_post(home, guests=3, split_cookeo="on")
    )

    assert response.status_code == 302 and MenuPlan.objects.count() == 1


def test_classic_mode_has_no_capacity_limit(owner_client, home):
    for name in range(9):
        Diner.objects.create(household=home, first_name=f"D{name}")

    response = owner_client.post(reverse("planner:generate"), form_post(home, mode="classic"))

    assert response.status_code == 302


def test_new_menu_form_proposes_classic_when_cookeo_is_missing(owner_client, home):
    HouseholdSettings.objects.create(household=home, source_mode="cookeo")

    page = owner_client.get(reverse("planner:new")).content.decode()

    assert re.search(r'<input[^>]*value="classic"[^>]*checked', page)
    assert not re.search(r'<input[^>]*value="cookeo"[^>]*checked', page)
    assert 'type="range"' in page


def test_settings_refuse_cookeo_mode_without_equipment(owner_client, home):
    data = {
        "meals": ["lunch"], "max_minutes_weekday": 30, "max_minutes_weekend": 60,
        "budget_level": 2, "min_repeat_days": 7, "vegetarian_per_week": 2,
        "source_mode": "mixed", "cookeo_share": 50,
    }  # fmt: skip

    response = owner_client.post(reverse("households:preferences"), data)

    assert (
        response.status_code == 200
        and "exige l&#x27;équipement Cookeo" in response.content.decode()
    )
    assert HouseholdSettings.objects.filter(household=home, source_mode="mixed").count() == 0


def test_recipe_page_shows_the_cookeo_programme(owner_client, home):
    gratin = Recipe.objects.get(title="Gratin dauphinois au Cookeo")
    plain = Recipe.objects.get(title="Gratin de courgettes")

    page = owner_client.get(reverse("catalog:detail", args=[gratin.pk])).content.decode()
    classic = owner_client.get(reverse("catalog:detail", args=[plain.pk])).content.decode()

    assert "Cuisson sous pression, 8 min sous pression" in page and "Extra Crisp" in page
    assert "Cookeo" not in classic.split("<h1>")[1].split("Ingrédients")[0]


def test_imported_cookeo_recipe_without_programme_says_so(owner_client, home):
    gratin = Recipe.objects.get(title="Gratin dauphinois au Cookeo")
    Recipe.objects.filter(pk=gratin.pk).update(cookeo_program={})

    page = owner_client.get(reverse("catalog:detail", args=[gratin.pk])).content.decode()

    assert "programme non précisé par la source" in page


def test_menu_marks_cookeo_meals(owner_client, home):
    HouseholdEquipment.objects.create(household=home, equipment_id=COOKEO)
    Diner.objects.create(household=home, first_name="Léa")
    plan = services.create_plan(home, request(home, mode="cookeo"), date(2026, 11, 2), seed=2)

    page = owner_client.get(reverse("planner:detail", args=[plan.pk])).content.decode()

    assert 'class="badge badge--accent">Cookeo' in page


def test_extra_crisp_is_recorded_for_the_two_recipes_that_use_it(db):
    from apps.catalog.starter import starter_recipes

    crisp = [r.title for r in starter_recipes() if r.cookeo_program.get("extra_crisp")]

    assert sorted(crisp) == ["Gratin dauphinois au Cookeo", "Hachis parmentier au Cookeo"]


def test_reloading_starter_recipes_propagates_reviewed_changes(db):
    from apps.catalog.starter import load_starter_recipes

    seed_catalog()
    Recipe.objects.filter(title="Riz pilaf au Cookeo").update(cookeo_program={}, steps=["ancien"])

    load_starter_recipes()

    recipe_ = Recipe.objects.get(title="Riz pilaf au Cookeo")
    assert recipe_.cookeo_program["pressure_minutes"] == 6 and recipe_.steps != ["ancien"]
