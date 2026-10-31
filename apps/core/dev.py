"""Outils de développement : connexion directe aux comptes de démonstration.

Jamais chargé en production : `config/urls.py` n'ajoute la route que si `DEV_LOGIN` est vrai, ce
que seuls les réglages locaux activent (un test le garantit).
"""

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_safe

DEMO_ACCOUNTS = {
    "proprietaire": "demo.proprietaire@menudujour.test",
    "membre": "demo.membre@menudujour.test",
    "nouveau": "demo.nouveau@menudujour.test",
}
AUTH_BACKEND = "allauth.account.auth_backends.AuthenticationBackend"


@require_safe
def dev_login(request: HttpRequest, role: str) -> HttpResponse:
    if not settings.DEV_LOGIN or role not in DEMO_ACCOUNTS:
        raise Http404
    user = get_user_model().objects.filter(email=DEMO_ACCOUNTS[role]).first()
    if user is None:
        raise Http404
    login(request, user, backend=AUTH_BACKEND)
    return redirect("core:home")
