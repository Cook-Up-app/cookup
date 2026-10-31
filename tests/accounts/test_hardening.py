import re

import pytest
from django.urls import reverse

from tests.conftest import make_user

EXECUTABLE_INLINE_SCRIPT = re.compile(
    r"<script(?![^>]*(?:\bsrc=|type=\"application/json\"))[^>]*>", re.I
)
MFA_PAGES = ["mfa_index", "mfa_activate_totp", "mfa_add_webauthn"]


@pytest.mark.django_db
@pytest.mark.parametrize("name", MFA_PAGES)
def test_mfa_pages_are_compatible_with_strict_csp(client, name, recent_reauth):
    """Pas de script inline exécutable : la CSP n'autorise que 'self'."""
    client.force_login(make_user("nomfa@example.com", mfa=False))

    response = client.get(reverse(name))

    assert response.status_code == 200
    assert not EXECUTABLE_INLINE_SCRIPT.search(response.content.decode())
    assert "unsafe-inline" not in response.headers["Content-Security-Policy"]


def test_admin_is_disabled_without_admin_path(production_settings):
    assert production_settings.ADMIN_PATH == ""
