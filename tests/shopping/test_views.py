from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Ingredient, Recipe
from apps.core.reference import Aisle
from apps.households.models import Diner, HouseholdEquipment, HouseholdSettings, Membership
from apps.planner import services as planner_services
from apps.planner.models import MenuPlan, MenuSlot
from apps.shopping import services
from apps.shopping.display import describe_quantity
from apps.shopping.models import PantryItem, ShoppingItem
from tests.conftest import make_user, seed_catalog

TODAY = timezone.localdate()


@pytest.fixture
def ready(owner_client, owner, db):
    seed_catalog()
    household = Membership.objects.get(user=owner).household
    plan = MenuPlan.objects.create(household=household, start_date=TODAY, end_date=TODAY, seed=1)
    MenuSlot.objects.create(
        plan=plan, day=TODAY, meal_type="dinner", servings=4,
        recipe=Recipe.objects.get(title="Gratin de courgettes"),
    )  # fmt: skip
    return owner_client, household, plan


def url(name, plan, *extra):
    return reverse(f"shopping:{name}", args=[plan.pk, *extra])


@pytest.mark.parametrize("name", ["shopping:aisles", "shopping:pantry"])
def test_pages_require_a_session(client, db, name):
    assert client.get(reverse(name)).status_code == 302


def test_list_shows_aisles_quantities_and_origin(ready):
    client, _, plan = ready

    page = client.get(url("detail", plan)).content.decode()

    assert "Fruits et légumes" in page and "Crèmerie" in page
    assert "courgette</span>" in page and "data-qty>4</span>" in page
    assert "Gratin de courgettes" in page
    assert "à acheter sur" in page


def test_simple_member_without_mfa_can_shop(client, ready):
    _, household, plan = ready
    member = make_user("member@example.com", mfa=False)
    Membership.objects.create(user=member, household=household)
    client.force_login(member)

    assert client.get(url("detail", plan)).status_code == 200


def test_checking_a_line_is_saved_immediately(ready):
    client, _, plan = ready
    client.get(url("detail", plan))
    item = ShoppingItem.objects.get(label="courgette")

    client.post(url("toggle", plan, item.pk))
    item.refresh_from_db()
    assert item.checked
    client.post(url("toggle", plan, item.pk))
    item.refresh_from_db()
    assert not item.checked


def test_removed_line_disappears_from_the_page(ready):
    client, _, plan = ready
    client.get(url("detail", plan))
    item = ShoppingItem.objects.get(label="courgette")

    client.post(url("remove", plan, item.pk))

    assert "courgette —" not in client.get(url("detail", plan)).content.decode()


def test_manual_item_can_be_added_and_survives_regeneration(ready):
    client, _, plan = ready

    client.post(
        url("add", plan), {"label": "Papier toilette", "quantity": "2", "aisle": Aisle.MISC}
    )
    response = client.post(url("regenerate", plan), follow=True)

    page = response.content.decode()
    assert "Papier toilette" in page and "ajouté à la main" in page and "Liste recalculée" in page


def test_invalid_manual_item_is_refused(ready):
    client, _, plan = ready

    client.post(url("add", plan), {"label": "  ", "aisle": "inconnu"})

    assert not ShoppingItem.objects.filter(manual=True).exists()


@pytest.mark.parametrize("name", ["regenerate", "add"])
def test_post_only_endpoints_reject_get(ready, name):
    client, _, plan = ready

    assert client.get(url(name, plan)).status_code == 405


@pytest.fixture
def foreign(ready, other_owner):
    other = Membership.objects.get(user=other_owner).household
    plan = MenuPlan.objects.create(household=other, start_date=TODAY, end_date=TODAY, seed=2)
    MenuSlot.objects.create(
        plan=plan, day=TODAY, meal_type="dinner", servings=4,
        recipe=Recipe.objects.get(title="Gratin de courgettes"),
    )  # fmt: skip
    services.sync_list(plan)
    pantry = PantryItem.objects.create(
        household=other, ingredient=Ingredient.objects.get(name="lait")
    )
    return plan, plan.shopping_list.items.first(), pantry


def test_foreign_plan_and_items_are_not_found(ready, foreign):
    client, _, mine = ready
    plan, item, _ = foreign
    client.get(url("detail", mine))

    assert client.get(url("detail", plan)).status_code == 404
    for name in ("regenerate", "add"):
        assert client.post(url(name, plan)).status_code == 404
    for name in ("toggle", "remove"):
        assert client.post(url(name, plan, item.pk)).status_code == 404
        assert client.post(url(name, mine, item.pk)).status_code == 404
    item.refresh_from_db()
    assert not item.checked and not item.hidden


def test_foreign_pantry_entries_cannot_be_removed(ready, foreign):
    client, _, _ = ready
    _, _, pantry = foreign

    assert client.post(reverse("shopping:pantry-remove", args=[pantry.pk])).status_code == 404
    assert PantryItem.objects.filter(pk=pantry.pk).exists()


def test_pantry_page_adds_updates_and_removes_entries(ready):
    client, household, _ = ready
    flour = Ingredient.objects.get(name="farine")

    client.post(reverse("shopping:pantry"), {"ingredient": flour.pk, "always_in_stock": "on"})
    client.post(reverse("shopping:pantry"), {"ingredient": flour.pk, "quantity": "500"})
    entry = PantryItem.objects.get(household=household, ingredient=flour)

    assert (entry.always_in_stock, entry.quantity, entry.unit) == (False, Decimal(500), "g")
    assert "farine" in client.get(reverse("shopping:pantry")).content.decode()
    client.post(reverse("shopping:pantry-remove", args=[entry.pk]))
    assert not PantryItem.objects.exists()


def test_aisle_order_is_remembered_per_household(ready):
    client, household, plan = ready
    ranks = {aisle: index + 1 for index, aisle in enumerate(reversed(Aisle.values))}

    client.post(reverse("shopping:aisles"), ranks)
    page = client.get(url("detail", plan)).content.decode()

    settings = HouseholdSettings.objects.get(household=household)
    assert (
        settings.aisle_order[0] == Aisle.MISC
        and settings.aisle_order[-1] == Aisle.FRUITS_VEGETABLES
    )
    assert page.index("Crèmerie") < page.index("Fruits et légumes")


def test_aisle_order_rejects_out_of_range_ranks(ready):
    client, household, _ = ready

    response = client.post(reverse("shopping:aisles"), {a: 99 for a in Aisle.values})

    assert response.status_code == 200
    assert (
        not HouseholdSettings.objects.filter(household=household).exclude(aisle_order=[]).exists()
    )


def test_page_stays_within_the_query_budget(ready, django_assert_max_num_queries):
    client, household, _ = ready
    for code in ("hob", "oven"):
        HouseholdEquipment.objects.create(household=household, equipment_id=code)
    Diner.objects.create(household=household, first_name="Léa")
    week = planner_services.create_plan(
        household,
        planner_services.PlanRequest(
            start_date=TODAY + timedelta(days=30), end_date=TODAY + timedelta(days=36),
            meals=("lunch", "dinner"), diner_ids=tuple(str(d.pk) for d in household.diners.all()),
        ),
        TODAY,
        seed=3,
    )  # fmt: skip
    client.get(url("detail", week))

    with django_assert_max_num_queries(15):
        assert client.get(url("detail", week)).status_code == 200


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((None, "", None, None, ""), ""),
        ((Decimal(500), "g", None, None, ""), "500 g"),
        ((Decimal(1500), "g", None, None, ""), "1,5 kg"),
        ((Decimal(2000), "ml", None, None, ""), "2 l"),
        ((Decimal(3), "pièce", None, None, ""), "3"),
        ((Decimal(650), "g", 2, Decimal(400), "boîte"), "2 boîtes de 400 g (≈ 650 g)"),
        ((Decimal(300), "g", 1, Decimal(400), "boîte"), "1 boîte de 400 g (≈ 300 g)"),
    ],
)
def test_quantity_text(args, expected):
    assert describe_quantity(*args) == expected
