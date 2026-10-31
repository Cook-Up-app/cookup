"""Parcours réel d'allauth : connexion, enrôlement TOTP, seconde étape."""

import time

import pytest
from allauth.mfa.totp.internal.auth import (
    SECRET_SESSION_KEY,
    format_hotp_value,
    hotp_value,
)
from django.urls import reverse

from apps.households import services
from tests.conftest import PASSWORD, make_user


def _code(secret: str, offset: int = 0) -> str:
    counter = int(time.time()) // 30 + offset
    return format_hotp_value(hotp_value(secret, counter))


@pytest.mark.django_db
def test_enrol_totp_then_second_factor_is_required_at_next_login(client, settings):
    settings.MFA_TOTP_TOLERANCE = 1  # le code d'activation est consommé : on prend celui d'après
    anna = make_user("anna@example.com", mfa=False)
    anna.is_staff = True
    anna.save()
    services.create_household(anna, "Foyer")

    client.post(reverse("account_login"), {"login": "anna@example.com", "password": PASSWORD})
    assert (
        client.get(reverse("households:home")).status_code == 302
    )  # MFA administrateur pas encore activée

    client.post(reverse("account_reauthenticate"), {"password": PASSWORD})
    client.get(reverse("mfa_activate_totp"))
    secret = client.session[SECRET_SESSION_KEY]
    client.post(reverse("mfa_activate_totp"), {"code": _code(secret)})
    client.post(reverse("account_logout"))

    login = client.post(
        reverse("account_login"), {"login": "anna@example.com", "password": PASSWORD}
    )
    assert "authenticate" in login["Location"]
    assert "_auth_user_id" not in client.session

    wrong = client.post(reverse("mfa_authenticate"), {"code": "000000"})
    assert wrong.status_code == 200
    assert "_auth_user_id" not in client.session

    client.post(reverse("mfa_authenticate"), {"code": _code(secret, offset=1)})
    assert client.session["_auth_user_id"]
    assert client.get(reverse("households:home")).status_code == 200
