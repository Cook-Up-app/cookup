from django.conf import settings
from django.http import HttpRequest
from django.urls import reverse

from . import navigation


def _entry(item: navigation.NavItem, view_name: str) -> dict:
    return {
        "label": item.label,
        "icon": item.icon,
        "url": reverse(navigation.url_for(item)),
        "active": navigation.is_active(item, view_name),
    }


def ui(request: HttpRequest) -> dict:
    """Entrées de navigation (avec l'entrée active) pour la coque de l'application."""
    match = getattr(request, "resolver_match", None)
    view_name = match.view_name if match else ""
    primary = [_entry(item, view_name) for item in navigation.PRIMARY]
    more = _entry(navigation.MORE, view_name)
    return {
        "nav_primary": primary,
        "nav_more": more,
        "nav_household": [_entry(i, view_name) for i in navigation.HOUSEHOLD],
        "nav_account": [_entry(i, view_name) for i in navigation.ACCOUNT],
        "signup_open": settings.SIGNUP_OPEN,
    }
