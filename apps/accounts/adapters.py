from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings
from django.http import HttpRequest


class SignupAdapter(DefaultAccountAdapter):
    """Inscription libre, fermable par `SIGNUP_OPEN` ; l'invitation reste dans `households`."""

    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return settings.SIGNUP_OPEN
