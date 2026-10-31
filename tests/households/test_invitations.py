from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.households import services
from apps.households.models import Invitation, Membership
from tests.conftest import PASSWORD, make_user

ACCEPT = {"display_name": "Léa", "password1": PASSWORD, "password2": PASSWORD}


def _invite(owner, email="lea@example.com"):
    household = Membership.objects.get(user=owner).household
    invitation, token = services.create_invitation(household, email, owner)
    return invitation, token


@pytest.mark.django_db
def test_token_is_stored_hashed_only(owner):
    invitation, token = _invite(owner)

    assert token not in invitation.token_hash
    assert len(invitation.token_hash) == 64


@pytest.mark.django_db
def test_invitation_expires_after_configured_days(owner, settings):
    invitation, _ = _invite(owner)

    delta = invitation.expires_at - timezone.now()
    assert (
        timedelta(days=settings.INVITATION_TTL_DAYS - 1)
        < delta
        <= timedelta(days=settings.INVITATION_TTL_DAYS)
    )


@pytest.mark.django_db
def test_accepting_creates_member_and_forces_mfa_enrolment(owner, client):
    invitation, token = _invite(owner)

    response = client.post(reverse("accept-invitation", args=[token]), ACCEPT)

    assert response.status_code == 302
    assert response["Location"] == reverse("mfa_index")
    user = User.objects.get(email="lea@example.com")
    assert Membership.objects.get(user=user).household == invitation.household
    assert Membership.objects.get(user=user).role == Membership.Role.MEMBER
    invitation.refresh_from_db()
    assert invitation.used_at is not None
    assert client.get(reverse("households:home")).status_code == 302  # MFA pas encore activée


@pytest.mark.django_db
def test_token_is_single_use(owner, client):
    _, token = _invite(owner)
    client.post(reverse("accept-invitation", args=[token]), ACCEPT)
    client.logout()

    response = client.get(reverse("accept-invitation", args=[token]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_expired_and_unknown_tokens_are_rejected(owner, client):
    invitation, token = _invite(owner)
    Invitation.objects.filter(pk=invitation.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )

    assert client.get(reverse("accept-invitation", args=[token])).status_code == 404
    assert client.get(reverse("accept-invitation", args=["inconnu"])).status_code == 404


@pytest.mark.django_db
def test_weak_password_is_refused(owner, client):
    _, token = _invite(owner)

    response = client.post(
        reverse("accept-invitation", args=[token]),
        {"display_name": "Léa", "password1": "court", "password2": "court"},
    )

    assert response.status_code == 200
    assert not User.objects.filter(email="lea@example.com").exists()


@pytest.mark.django_db
def test_invitation_for_existing_account_is_refused(owner, client):
    make_user("lea@example.com")
    _, token = _invite(owner)

    assert client.post(reverse("accept-invitation", args=[token]), ACCEPT).status_code == 404


@pytest.mark.django_db
def test_only_owner_can_create_invitations(owner, client):
    member = make_user("member@example.com")
    Membership.objects.create(user=member, household=Membership.objects.get(user=owner).household)
    client.force_login(member)

    response = client.post(reverse("households:invitation-create"), {"email": "x@example.com"})

    assert response.status_code == 404
    assert not Invitation.objects.exists()


@pytest.mark.django_db
def test_owner_sees_invitation_link_once(owner_client):
    response = owner_client.post(
        reverse("households:invitation-create"), {"email": "lea@example.com"}, follow=True
    )

    assert "/invitation/" in response.content.decode()
    assert "/invitation/" not in owner_client.get(reverse("households:home")).content.decode()


@pytest.mark.django_db
def test_new_member_can_enrol_mfa_without_logging_in_again(owner, client):
    _, token = _invite(owner)
    client.post(reverse("accept-invitation", args=[token]), ACCEPT)

    assert client.get(reverse("mfa_activate_totp")).status_code == 200
