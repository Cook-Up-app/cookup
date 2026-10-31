"""Accès au foyer courant et contrôle des rôles (le propriétaire gère, les membres consultent)."""

from collections.abc import Callable
from functools import wraps

from django.http import Http404, HttpRequest, HttpResponse

from .models import Membership
from .services import ensure_household

SESSION_HOUSEHOLD_KEY = "household_id"


def current_membership(request: HttpRequest) -> Membership | None:
    """Adhésion du foyer actif : celui choisi en session s'il reste valide, sinon le premier."""
    if hasattr(request, "_membership"):
        return request._membership
    memberships = Membership.objects.filter(user=request.user).select_related("household")
    chosen = request.session.get(SESSION_HOUSEHOLD_KEY)
    membership = memberships.filter(household_id=chosen).first() if chosen else None
    request._membership = membership or memberships.first()
    return request._membership


def household_required(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    @wraps(view)
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        membership = current_membership(request) or ensure_household(request.user)
        request.membership = membership
        request.household = membership.household
        return view(request, *args, **kwargs)

    return wrapper


def owner_required(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    @household_required
    @wraps(view)
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not request.membership.is_owner:
            raise Http404  # ne révèle pas l'existence de la ressource
        return view(request, *args, **kwargs)

    return wrapper
