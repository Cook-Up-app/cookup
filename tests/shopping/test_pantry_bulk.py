"""Placard : cocher plusieurs produits toujours en stock et tout enregistrer d'un coup."""

import pytest
from django.urls import reverse

from apps.catalog.models import Ingredient
from apps.core.reference import Aisle
from apps.households.models import Household, Membership
from apps.shopping.forms import PantryBulkForm
from apps.shopping.models import PantryItem
from tests.conftest import make_user

URL = "shopping:pantry-bulk-add"


@pytest.fixture
def stock(db):
    def make(name, aisle=Aisle.SAVORY_GROCERY, **extra):
        return Ingredient.objects.create(
            name=name, normalized_name=name.lower(), aisle=aisle, **extra
        )

    return {
        "riz": make("riz"),
        "pâtes": make("pâtes"),
        "lait": make("lait", Aisle.DAIRY),
        "sel": make("sel", Aisle.CONDIMENTS_SPICES, is_staple=True),
    }


@pytest.fixture
def household(owner):
    return Membership.objects.get(user=owner).household


def _post(client, **fields):
    return client.post(reverse(URL), fields)


@pytest.mark.django_db
def test_several_products_are_added_in_one_submission(owner_client, household, stock):
    response = _post(
        owner_client,
        **{
            "aisle_savory_grocery": [str(stock["riz"].pk), str(stock["pâtes"].pk)],
            "aisle_dairy": [str(stock["lait"].pk)],
        },
    )

    assert response.status_code == 302
    items = PantryItem.objects.filter(household=household)
    assert set(items.values_list("ingredient__name", flat=True)) == {"riz", "pâtes", "lait"}
    assert all(item.always_in_stock for item in items)


@pytest.mark.django_db
def test_the_confirmation_counts_the_products(owner_client, stock):
    response = owner_client.post(
        reverse(URL),
        {"aisle_savory_grocery": [str(stock["riz"].pk), str(stock["pâtes"].pk)]},
        follow=True,
    )

    assert "2 produits ajoutés au placard." in response.content.decode()


@pytest.mark.django_db
def test_staples_and_stocked_products_are_not_offered(household, stock):
    PantryItem.objects.create(household=household, ingredient=stock["riz"])

    form = PantryBulkForm(household=household)
    offered = {label for field in form.fields.values() for _, label in field.choices}

    assert offered == {"pâtes", "lait"}  # ni « sel » (produit de base) ni « riz » (déjà là)


@pytest.mark.django_db
def test_existing_items_keep_their_quantity(owner_client, household, stock):
    PantryItem.objects.create(
        household=household, ingredient=stock["riz"], always_in_stock=False, quantity=500, unit="g"
    )

    _post(owner_client, aisle_savory_grocery=[str(stock["riz"].pk)])

    item = PantryItem.objects.get(household=household, ingredient=stock["riz"])
    assert item.quantity == 500 and not item.always_in_stock


@pytest.mark.django_db
def test_nothing_checked_is_refused(owner_client, stock):
    response = _post(owner_client)

    assert response.status_code == 200
    assert "Cochez au moins un produit" in response.content.decode()
    assert not PantryItem.objects.exists()


@pytest.mark.django_db
def test_unknown_ids_and_wrong_aisles_are_refused(owner_client, stock):
    _post(owner_client, aisle_savory_grocery=["999999"])
    _post(owner_client, aisle_dairy=[str(stock["riz"].pk)])  # riz n'est pas dans ce rayon
    _post(owner_client, aisle_savory_grocery=["abc"])

    assert not PantryItem.objects.exists()


@pytest.mark.django_db
def test_the_other_household_is_untouched(owner_client, other_owner, stock):
    other = Membership.objects.get(user=other_owner).household
    PantryItem.objects.create(household=other, ingredient=stock["lait"])

    _post(owner_client, aisle_savory_grocery=[str(stock["riz"].pk)])

    assert PantryItem.objects.filter(household=other).count() == 1


@pytest.mark.django_db
def test_get_is_not_allowed_and_anonymous_is_redirected(client, owner_client):
    assert owner_client.get(reverse(URL)).status_code == 405
    anonymous = type(client)()
    assert anonymous.post(reverse(URL), {})["Location"].startswith(reverse("account_login"))


@pytest.mark.django_db
def test_a_household_member_can_fill_the_pantry(client, owner, household, stock):
    member = make_user("member@example.com", mfa=False)
    Membership.objects.create(user=member, household=household)
    client.force_login(member)

    client.post(reverse(URL), {"aisle_savory_grocery": [str(stock["riz"].pk)]})

    assert PantryItem.objects.filter(household=household).count() == 1
    assert Household.objects.count() >= 1


@pytest.mark.django_db
def test_the_page_lists_products_by_aisle_with_a_filter(owner_client, stock):
    page = owner_client.get(reverse("shopping:pantry")).content.decode()

    assert "data-filter-input" in page and "Épicerie salée" in page and "Crèmerie" in page
    assert "<span>riz</span>" in page and "<span>sel</span>" not in page  # pastilles : hors base


@pytest.mark.django_db
def test_the_pantry_page_stays_within_the_query_budget(
    owner_client, stock, django_assert_max_num_queries
):
    with django_assert_max_num_queries(15):
        assert owner_client.get(reverse("shopping:pantry")).status_code == 200
