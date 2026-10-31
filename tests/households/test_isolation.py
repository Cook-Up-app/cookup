"""Un utilisateur ne peut ni lire ni modifier les objets d'un autre foyer (IDOR)."""

import pytest
from django.urls import reverse

from apps.core.reference import Allergen
from apps.households import services
from apps.households.models import Diner, DinerRestriction, Invitation, Membership
from tests.conftest import make_user


@pytest.fixture
def foreign(other_owner):
    """Données privées du foyer B, que le propriétaire du foyer A ne doit pas atteindre."""
    household = Membership.objects.get(user=other_owner).household
    diner = Diner.objects.create(household=household, first_name="Secret")
    restriction = DinerRestriction.objects.create(diner=diner, allergen=Allergen.PEANUTS)
    invitation, _ = services.create_invitation(household, "x@example.com", other_owner)
    membership = Membership.objects.get(user=other_owner)
    return {
        "diner": diner,
        "restriction": restriction,
        "invitation": invitation,
        "membership": membership,
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "name", "key"),
    [
        ("get", "households:diner", "diner"),
        ("post", "households:diner", "diner"),
        ("post", "households:diner-delete", "diner"),
        ("post", "households:restriction-add", "diner"),
        ("post", "households:restriction-delete", "restriction"),
        ("post", "households:invitation-revoke", "invitation"),
    ],
)
def test_foreign_objects_are_not_found(owner_client, foreign, method, name, key):
    url = reverse(name, args=[foreign[key].pk])

    response = getattr(owner_client, method)(url, {"first_name": "Pirate", "allergen": "milk"})

    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["households:member-remove", "households:member-reset-link"])
def test_foreign_members_are_not_found(owner_client, foreign, recent_reauth, name):
    response = owner_client.post(reverse(name, args=[foreign["membership"].pk]))

    assert response.status_code == 404
    assert Membership.objects.filter(pk=foreign["membership"].pk).exists()


@pytest.mark.django_db
def test_foreign_data_is_never_modified(owner_client, foreign):
    owner_client.post(
        reverse("households:diner", args=[foreign["diner"].pk]), {"first_name": "Pirate"}
    )
    owner_client.post(reverse("households:diner-delete", args=[foreign["diner"].pk]))

    foreign["diner"].refresh_from_db()
    assert foreign["diner"].first_name == "Secret"
    assert DinerRestriction.objects.filter(pk=foreign["restriction"].pk).exists()
    assert Invitation.objects.filter(pk=foreign["invitation"].pk).exists()


@pytest.mark.django_db
def test_lists_do_not_leak_other_households(owner_client, foreign):
    for name in ("households:diners", "households:home"):
        assert "Secret" not in owner_client.get(reverse(name)).content.decode()


@pytest.mark.django_db
def test_for_household_filters_every_private_model(owner, foreign):
    household = Membership.objects.get(user=owner).household

    assert not Diner.objects.for_household(household).exists()
    assert not DinerRestriction.objects.for_household(household).exists()
    assert not Invitation.objects.for_household(household).exists()
    assert Membership.objects.for_household(household).count() == 1


@pytest.mark.django_db
def test_members_cannot_manage_diners_or_allergies(owner, client):
    household = Membership.objects.get(user=owner).household
    diner = Diner.objects.create(household=household, first_name="Léa")
    member = make_user("member@example.com")
    Membership.objects.create(user=member, household=household)
    client.force_login(member)

    assert client.get(reverse("households:diner", args=[diner.pk])).status_code == 200
    client.post(reverse("households:diner", args=[diner.pk]), {"first_name": "Hack"})
    assert (
        client.post(
            reverse("households:restriction-add", args=[diner.pk]), {"allergen": "milk"}
        ).status_code
        == 404
    )
    assert client.post(reverse("households:diner-delete", args=[diner.pk])).status_code == 404
    client.post(reverse("households:diners"), {"first_name": "Intrus"})

    diner.refresh_from_db()
    assert diner.first_name == "Léa"
    assert Diner.objects.count() == 1
