import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.households import services
from apps.households.models import Membership
from tests.conftest import PASSWORD, make_user

PROTECTED = [
    "core:home",
    "households:home",
    "households:diners",
    "households:equipment",
    "mfa_index",
]


@pytest.mark.django_db
@pytest.mark.parametrize("name", PROTECTED)
def test_anonymous_is_redirected_to_login(client, name):
    response = client.get(reverse(name))

    assert response.status_code == 302
    assert response["Location"].startswith(reverse("account_login"))


PAGES_BEHIND_MFA = [n for n in PROTECTED if n != "mfa_index"]


def _owner_without_mfa(email: str = "nomfa@example.com"):
    user = make_user(email, mfa=False)
    services.create_household(user, "Foyer")
    return user


@pytest.mark.django_db
@pytest.mark.parametrize("name", PAGES_BEHIND_MFA)
def test_owner_without_mfa_is_sent_to_enrolment(client, name):
    client.force_login(_owner_without_mfa())

    response = client.get(reverse(name))

    assert response.status_code == 302
    assert response["Location"].startswith(reverse("mfa_index"))


@pytest.mark.django_db
def test_staff_without_mfa_is_sent_to_enrolment(client):
    user = make_user("staff@example.com", mfa=False)
    user.is_staff = True
    user.save()
    client.force_login(user)

    response = client.get(reverse("core:home"))

    assert response.status_code == 302
    assert response["Location"].startswith(reverse("mfa_index"))


@pytest.mark.django_db
@pytest.mark.parametrize("name", PAGES_BEHIND_MFA)
def test_simple_member_does_not_need_mfa(client, name):
    owner = _owner_without_mfa("boss@example.com")
    member = make_user("member@example.com", mfa=False)
    Membership.objects.create(user=member, household=Membership.objects.get(user=owner).household)
    client.force_login(member)

    assert client.get(reverse(name)).status_code == 200


@pytest.mark.django_db
def test_admin_can_reach_enrolment_page(client):
    client.force_login(_owner_without_mfa())

    assert client.get(reverse("mfa_index")).status_code == 200


@pytest.mark.django_db
def test_user_with_mfa_has_access(owner_client):
    assert owner_client.get(reverse("households:home")).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["core:health", "account_login"])
def test_public_routes_stay_public(client, name):
    assert client.get(reverse(name)).status_code == 200


@pytest.mark.django_db
def test_french_paths_are_used():
    assert reverse("account_login") == "/connexion"
    assert reverse("account_logout") == "/deconnexion"
    assert reverse("mfa_index") == "/compte/securite"


@pytest.mark.django_db
def test_public_signup_is_closed(client):
    client.post(
        "/compte/signup/",
        {"email": "new@example.com", "password1": PASSWORD, "password2": PASSWORD},
    )

    assert not User.objects.filter(email="new@example.com").exists()


@pytest.mark.django_db
def test_passwords_are_hashed_with_argon2(db):
    assert make_user("a@example.com").password.startswith("argon2$")


@pytest.mark.django_db
def test_login_requires_second_factor_when_enrolled(client):
    make_user("mfa@example.com")

    response = client.post(
        reverse("account_login"), {"login": "mfa@example.com", "password": PASSWORD}
    )

    assert response.status_code == 302
    assert "authenticate" in response["Location"]
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_login_error_is_identical_for_unknown_email_and_wrong_password(client):
    make_user("known@example.com")

    unknown = client.post(
        reverse("account_login"), {"login": "ghost@example.com", "password": "x" * 14}
    )
    wrong = client.post(
        reverse("account_login"), {"login": "known@example.com", "password": "y" * 14}
    )

    assert unknown.status_code == wrong.status_code == 200
    assert unknown.context["form"].errors == wrong.context["form"].errors
