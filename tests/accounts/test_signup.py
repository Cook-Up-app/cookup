import pytest
from django.core.cache import cache
from django.urls import reverse

from apps.accounts.middleware import mfa_required
from apps.accounts.models import User
from apps.households.models import Household, Membership
from tests.conftest import PASSWORD, make_user

SIGNUP = {
    "display_name": "Alice",
    "email": "alice@example.com",
    "password1": PASSWORD,
    "password2": PASSWORD,
}


@pytest.fixture(autouse=True)
def _clean_rate_limits(db):
    cache.clear()


def _signup(client, **overrides):
    return client.post(reverse("account_signup"), {**SIGNUP, **overrides})


@pytest.mark.django_db
def test_signup_page_is_public_and_in_french(client):
    response = client.get(reverse("account_signup"))

    assert response.status_code == 200
    assert "Créer un compte" in response.content.decode()
    assert reverse("account_signup") == "/inscription"


@pytest.mark.django_db
def test_signup_creates_a_logged_in_user_with_their_own_household(client):
    other = make_user("host@example.com")
    host_household = Membership.objects.create(
        user=other, household=Household.objects.create(name="Chez l'hôte"), role="owner"
    ).household

    response = _signup(client)

    assert response.status_code == 302
    user = User.objects.get(email="alice@example.com")
    assert user.display_name == "Alice" and not user.is_staff
    assert client.get(reverse("core:home")).status_code in (200, 302)
    membership = Membership.objects.get(user=user)
    assert membership.is_owner and membership.household != host_household
    assert Membership.objects.filter(household=membership.household).count() == 1


@pytest.mark.django_db
def test_new_user_never_sees_another_household(client):
    host = make_user("host@example.com")
    Membership.objects.create(user=host, household=Household.objects.create(name="Secret"))
    _signup(client)

    page = client.get(reverse("households:home")).content.decode()

    assert "Secret" not in page and "host@example.com" not in page


@pytest.mark.django_db
def test_simple_user_is_not_forced_to_enrol_a_second_factor(client):
    _signup(client)

    assert client.get(reverse("households:home")).status_code == 200
    assert not mfa_required(User.objects.get(email="alice@example.com"))


@pytest.mark.django_db
def test_staff_still_requires_mfa():
    assert mfa_required(User(is_staff=True))
    assert mfa_required(User(is_superuser=True))


@pytest.mark.django_db
def test_signup_cannot_grant_staff_or_pick_a_household(client):
    _signup(client, is_staff="on", is_superuser="on", household="1")

    user = User.objects.get(email="alice@example.com")
    assert not user.is_staff and not user.is_superuser


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "not-an-email"},
        {"password2": "different-password-123"},
        {"password1": "short", "password2": "short"},
        {"display_name": ""},
    ],
)
def test_invalid_signup_creates_nothing(client, overrides):
    response = _signup(client, **overrides)

    assert response.status_code == 200
    assert not User.objects.filter(email__iexact=SIGNUP["email"]).exists()


@pytest.mark.django_db
def test_signup_refuses_an_existing_email_in_any_case(client):
    make_user("alice@example.com")

    response = _signup(client, email="ALICE@example.com")

    assert response.status_code == 200
    assert User.objects.filter(email__iexact="alice@example.com").count() == 1


@pytest.mark.django_db
def test_signup_is_rate_limited_per_ip(client):
    for index in range(5):
        _signup(client, email=f"user{index}@example.com")
        client.logout()

    response = _signup(client, email="one-too-many@example.com")

    assert not User.objects.filter(email="one-too-many@example.com").exists()
    assert "Trop de tentatives" in response.content.decode()


@pytest.mark.django_db
def test_signup_can_be_closed_and_the_login_link_disappears(client, settings):
    settings.SIGNUP_OPEN = False

    assert "Créer un compte" not in client.get(reverse("account_login")).content.decode()
    _signup(client)
    assert not User.objects.filter(email="alice@example.com").exists()


@pytest.mark.django_db
def test_login_page_links_to_signup_when_open(client):
    assert reverse("account_signup") in client.get(reverse("account_login")).content.decode()


@pytest.mark.django_db
def test_invitation_still_adds_to_the_inviting_household(client, owner):
    from apps.households import services

    household = Membership.objects.get(user=owner).household
    _, token = services.create_invitation(household, "guest@example.com", owner)

    client.post(
        reverse("accept-invitation", args=[token]),
        {"display_name": "Invité", "password1": PASSWORD, "password2": PASSWORD},
    )

    guest = User.objects.get(email="guest@example.com")
    assert Membership.objects.get(user=guest).household == household
