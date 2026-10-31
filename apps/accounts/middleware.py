"""Refus par défaut : toute route exige une session ; les administrateurs ont aussi la MFA."""

from collections.abc import Callable

from allauth.mfa.models import Authenticator
from allauth.mfa.utils import is_mfa_enabled
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse
from django.urls import Resolver404, resolve

from apps.households.models import Membership

# Accessibles sans session : connexion, réinitialisation par lien, invitation, santé, cron.
PUBLIC_URL_NAMES = frozenset(
    {
        "account_login",
        "account_logout",
        "account_signup",
        "account_inactive",
        "account_confirm_login_code",
        "account_reset_password",
        "account_reset_password_done",
        "account_reset_password_from_key",
        "account_reset_password_from_key_done",
        "mfa_authenticate",
        "mfa_login_webauthn",
        "accept-invitation",
        "health",
        "cron-daily",
        "cron-import",
    }
)

# Accessibles avec une session mais sans MFA enrôlée : c'est ici qu'on l'active.
MFA_ENROLMENT_URL_NAMES = frozenset(
    {
        "mfa_index",
        "mfa_activate_totp",
        "mfa_list_webauthn",
        "mfa_add_webauthn",
        "mfa_view_recovery_codes",
        "mfa_generate_recovery_codes",
        "mfa_download_recovery_codes",
        "mfa_reauthenticate",
        "mfa_reauthenticate_webauthn",
        "account_reauthenticate",
    }
)

# Types de second facteur qui comptent (les codes de récupération seuls ne suffisent pas).
SECOND_FACTOR_TYPES = [Authenticator.Type.TOTP, Authenticator.Type.WEBAUTHN]


def mfa_required(user) -> bool:
    """MFA obligatoire pour les administrateurs (staff ou propriétaire de foyer), facultative sinon.

    Un simple membre qui active tout de même une MFA se verra la demander à la connexion.
    """
    if user.is_staff or user.is_superuser:
        return True
    return Membership.objects.filter(user=user, role=Membership.Role.OWNER).exists()


class AccessPolicyMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        denial = self._denial(request)
        return denial if denial is not None else self.get_response(request)

    def _denial(self, request: HttpRequest) -> HttpResponse | None:
        url_name = self._url_name(request)
        if url_name is None or url_name in PUBLIC_URL_NAMES:
            return None
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        if url_name in MFA_ENROLMENT_URL_NAMES or not mfa_required(request.user):
            return None
        if is_mfa_enabled(request.user, types=SECOND_FACTOR_TYPES):
            return None
        return redirect_to_login(request.get_full_path(), "mfa_index")

    @staticmethod
    def _url_name(request: HttpRequest) -> str | None:
        try:
            return resolve(request.path_info).url_name
        except Resolver404:
            return None  # 404 normale, rien à protéger
