from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe


@require_safe
def password_reset_disabled(request: HttpRequest) -> HttpResponse:
    """Sans e-mail, le propriétaire du foyer génère le lien de réinitialisation."""
    return render(request, "accounts/password_reset_disabled.html")
