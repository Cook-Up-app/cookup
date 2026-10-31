from datetime import date, timedelta

import pytest

from apps.catalog.models import Ingredient, Recipe
from apps.core.reference import Aisle
from apps.households import services as household_services
from apps.households.models import Membership
from apps.planner.models import MenuPlan, MenuSlot
from apps.shopping import services
from apps.shopping.models import PantryItem, ShoppingItem
from tests.conftest import make_user, seed_catalog

DAY = date(2026, 11, 2)


@pytest.fixture
def home(db):
    seed_catalog()
    user = make_user("boss@example.com")
    household_services.create_household(user, "Foyer")
    return Membership.objects.get().household


def make_plan(home, titles=("Gratin de courgettes",), servings=4) -> MenuPlan:
    plan = MenuPlan.objects.create(household=home, start_date=DAY, end_date=DAY, seed=1)
    for index, title in enumerate(titles):
        MenuSlot.objects.create(
            plan=plan,
            day=DAY + timedelta(days=index),
            meal_type="dinner",
            recipe=Recipe.objects.get(title=title),
            servings=servings,
        )
    return plan


def by_label(shopping_list, label):
    return shopping_list.items.get(label=label)


def test_list_is_built_from_the_menu_scaled_to_the_servings(home):
    plan = make_plan(home, servings=8)  # la recette est pour 4 : tout double

    shopping_list = services.sync_list(plan)

    courgettes = by_label(shopping_list, "courgette")
    assert (courgettes.quantity, courgettes.unit) == (8, "pièce")
    assert by_label(shopping_list, "crème liquide").quantity == 400  # 20 cl × 2


def test_staples_are_not_listed_and_lines_know_their_recipes(home):
    shopping_list = services.sync_list(make_plan(home))

    assert not shopping_list.items.filter(label__in=["sel", "poivre"]).exists()
    assert by_label(shopping_list, "courgette").recipes[0][1] == "Gratin de courgettes"


def test_same_ingredient_across_meals_is_added_up(home):
    plan = make_plan(home, ("Gratin de courgettes", "Quiche aux légumes"))

    shopping_list = services.sync_list(plan)

    assert by_label(shopping_list, "courgette").quantity == 6  # 4 + 2
    assert len(by_label(shopping_list, "courgette").recipes) == 2


def test_leftover_servings_are_cooked_with_the_dinner(home):
    plan = MenuPlan.objects.create(
        household=home, start_date=DAY, end_date=DAY + timedelta(days=1), seed=1
    )
    recipe = Recipe.objects.get(title="Gratin de courgettes")
    MenuSlot.objects.create(plan=plan, day=DAY, meal_type="dinner", recipe=recipe, servings=4)
    MenuSlot.objects.create(
        plan=plan,
        day=DAY + timedelta(days=1),
        meal_type="lunch",
        recipe=recipe,
        servings=4,
        leftover=True,
    )

    shopping_list = services.sync_list(plan)

    assert by_label(shopping_list, "courgette").quantity == 8  # 4 + 4 de restes, une seule fois


def test_out_of_home_and_empty_slots_add_nothing(home):
    plan = make_plan(home)
    MenuSlot.objects.create(plan=plan, day=DAY, meal_type="lunch", out_of_home=True)

    assert services.sync_list(plan).items.count() > 0
    MenuSlot.objects.filter(plan=plan).update(recipe=None)
    assert services.sync_list(plan).items.count() == 0


def test_regeneration_keeps_checked_boxes_and_manual_lines(home):
    plan = make_plan(home, ("Gratin de courgettes", "Quiche aux légumes"))
    shopping_list = services.sync_list(plan)
    services.toggle_checked(by_label(shopping_list, "courgette"))
    services.toggle_checked(by_label(shopping_list, "crème liquide"))
    manual = services.add_manual_item(shopping_list, "Papier toilette", None, Aisle.MISC)
    MenuSlot.objects.filter(recipe__title="Quiche aux légumes").delete()  # le menu change

    services.sync_list(plan)

    assert by_label(shopping_list, "courgette").checked  # ligne restante : case conservée
    assert by_label(shopping_list, "courgette").quantity == 4  # recalculée
    assert by_label(shopping_list, "crème liquide").checked
    assert not shopping_list.items.filter(label="poivron").exists()  # ligne disparue : retirée
    manual.refresh_from_db()
    assert manual.manual and not shopping_list.items.filter(label="poivron").exists()


def test_removed_lines_do_not_come_back(home):
    plan = make_plan(home)
    shopping_list = services.sync_list(plan)
    services.remove_item(by_label(shopping_list, "courgette"))

    services.sync_list(plan)

    assert by_label(shopping_list, "courgette").hidden


def test_manual_line_removal_deletes_it(home):
    shopping_list = services.sync_list(make_plan(home))
    manual = services.add_manual_item(shopping_list, "Piles")

    services.remove_item(manual)

    assert not ShoppingItem.objects.filter(pk=manual.pk).exists()


def test_list_refreshes_itself_when_the_menu_changed(home):
    plan = make_plan(home)
    first = services.list_for(plan)
    count = first.items.count()
    MenuSlot.objects.filter(plan=plan).update(recipe=Recipe.objects.get(title="Quiche aux légumes"))

    refreshed = services.list_for(plan)

    assert refreshed.pk == first.pk and refreshed.items.count() != count
    assert services.list_for(plan).signature == refreshed.signature


def test_pantry_removes_and_deducts(home):
    plan = make_plan(home)
    cream = Ingredient.objects.get(name="crème liquide")
    PantryItem.objects.create(household=home, ingredient=cream, always_in_stock=True)
    onion_free = Ingredient.objects.get(name="fromage râpé")
    PantryItem.objects.create(
        household=home, ingredient=onion_free, always_in_stock=False, quantity=60, unit="g"
    )

    shopping_list = services.sync_list(plan)

    assert not shopping_list.items.filter(label="crème liquide").exists()
    assert by_label(shopping_list, "fromage râpé").quantity == 40  # 100 g − 60 g en stock


def test_a_staple_can_be_added_back_to_the_list(home):
    plan = make_plan(home)
    salt = Ingredient.objects.get(name="sel")
    PantryItem.objects.create(household=home, ingredient=salt, always_in_stock=False)

    assert services.sync_list(plan).items.filter(label="sel").exists()


def test_aisles_are_taken_from_the_catalogue(home):
    shopping_list = services.sync_list(make_plan(home))

    assert by_label(shopping_list, "courgette").aisle == Aisle.FRUITS_VEGETABLES
    assert by_label(shopping_list, "crème liquide").aisle == Aisle.DAIRY
