from allauth.account.adapter import DefaultAccountAdapter
from django.http import HttpRequest


class ClosedAccountAdapter(DefaultAccountAdapter):
    """Pas d'inscription publique : les comptes naissent d'une invitation (households)."""

    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return False
