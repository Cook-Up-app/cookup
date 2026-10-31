import re

import pytest
from django.urls import reverse

from apps.core.reference import Allergen
from apps.core.reference import Equipment as EquipmentReference
from apps.households import services
from apps.households.exceptions import LastOwnerError
from apps.households.models import (
    Diner,
    DinerRestriction,
    Equipment,
    HouseholdEquipment,
    Membership,
)
from tests.conftest import make_user

NEW_PASSWORD = "another-strong-passphrase"


@pytest.mark.django_db
def test_user_without_household_can_create_one(client):
    client.force_login(make_user("new@example.com"))

    client.post(
        reverse("households:home"),
        {"name": "Chez nous", "default_servings": 4, "week_start_day": 0},
    )

    membership = Membership.objects.get(user__email="new@example.com")
    assert membership.is_owner
    assert membership.household.name == "Chez nous"


@pytest.mark.django_db
def test_owner_adds_diner_with_strict_allergy(owner_client):
    response = owner_client.post(
        reverse("households:diners"),
        {"first_name": "Léa", "age_group": "child", "diets": ["vegetarian"]},
    )
    diner = Diner.objects.get(first_name="Léa")
    owner_client.post(
        reverse("households:restriction-add", args=[diner.pk]),
        {"allergen": Allergen.TREE_NUTS, "severity": "strict_allergy"},
    )

    assert response.status_code == 302
    assert diner.diets == ["vegetarian"]
    assert DinerRestriction.objects.get(diner=diner).allergen == Allergen.TREE_NUTS


@pytest.mark.django_db
def test_restriction_requires_a_target(owner_client):
    diner = Diner.objects.create(household=Membership.objects.get().household, first_name="Léa")

    owner_client.post(reverse("households:restriction-add", args=[diner.pk]), {"severity": "avoid"})

    assert not DinerRestriction.objects.exists()


@pytest.mark.django_db
def test_equipment_catalogue_is_seeded_from_reference():
    assert set(Equipment.objects.values_list("code", flat=True)) == set(EquipmentReference.values)


@pytest.mark.django_db
def test_owner_sets_household_equipment(owner_client):
    owner_client.post(
        reverse("households:equipment"), {"equipment": [EquipmentReference.COOKEO, "oven"]}
    )
    owner_client.post(reverse("households:equipment"), {"equipment": ["oven"]})

    assert list(HouseholdEquipment.objects.values_list("equipment_id", flat=True)) == ["oven"]


@pytest.mark.django_db
def test_last_owner_cannot_be_removed(owner):
    with pytest.raises(LastOwnerError):
        services.remove_member(Membership.objects.get(user=owner))


@pytest.mark.django_db
def test_removing_a_member_requires_recent_reauthentication(owner_client, owner):
    member = make_user("member@example.com")
    membership = Membership.objects.create(
        user=member, household=Membership.objects.get(user=owner).household
    )

    response = owner_client.post(reverse("households:member-remove", args=[membership.pk]))

    assert response.status_code == 302
    assert "reauthenticate" in response["Location"]
    assert Membership.objects.filter(pk=membership.pk).exists()


@pytest.mark.django_db
def test_owner_removes_member_after_reauthentication(owner_client, owner, recent_reauth):
    member = make_user("member@example.com")
    membership = Membership.objects.create(
        user=member, household=Membership.objects.get(user=owner).household
    )

    owner_client.post(reverse("households:member-remove", args=[membership.pk]))

    assert not Membership.objects.filter(pk=membership.pk).exists()


@pytest.mark.django_db
def test_owner_generated_reset_link_changes_password_but_keeps_mfa(
    owner_client, owner, recent_reauth, client
):
    member = make_user("member@example.com")
    membership = Membership.objects.create(
        user=member, household=Membership.objects.get(user=owner).household
    )
    page = owner_client.post(
        reverse("households:member-reset-link", args=[membership.pk]), follow=True
    )
    link = re.search(r"(/compte/password/reset/key/[^\s<]+)", page.content.decode()).group(1)

    form_page = client.get(link, follow=True)
    client.post(
        form_page.request["PATH_INFO"], {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD}
    )
    member.refresh_from_db()
    login = client.post(
        reverse("account_login"), {"login": "member@example.com", "password": NEW_PASSWORD}
    )

    assert member.check_password(NEW_PASSWORD)
    assert "authenticate" in login["Location"]  # la MFA reste exigée après réinitialisation
