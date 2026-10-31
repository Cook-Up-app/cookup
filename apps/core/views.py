import hmac

from django.conf import settings
from django.db import Error as DatabaseError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_safe

from apps.sources.weekly import run_weekly_import

from . import services

BEARER_PREFIX = "Bearer "


@require_safe
def home(request: HttpRequest) -> HttpResponse:
    return render(request, "home.html")


@require_safe
def health(request: HttpRequest) -> JsonResponse:
    """État de l'application, sans donnée sensible."""
    try:
        services.check_database()
    except DatabaseError:
        return JsonResponse({"status": "degraded", "database": "down"}, status=503)
    return JsonResponse({"status": "ok", "database": "up"})


def _is_authorized_cron(request: HttpRequest) -> bool:
    expected = settings.CRON_SECRET
    header = request.headers.get("Authorization", "")
    if not expected or not header.startswith(BEARER_PREFIX):
        return False
    return hmac.compare_digest(header[len(BEARER_PREFIX) :], expected)


@require_GET
def cron_daily(request: HttpRequest) -> JsonResponse:
    """Tâche quotidienne Vercel Cron ; en M0 : maintien de la base active."""
    if not _is_authorized_cron(request):
        return JsonResponse({"detail": "Non autorisé."}, status=401)
    try:
        services.keep_database_alive()
    except DatabaseError:
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok"})


@require_GET
def cron_import(request: HttpRequest) -> JsonResponse:
    """Import hebdomadaire de recettes (Vercel Cron) ; peut être rappelé pour vider la file."""
    if not _is_authorized_cron(request):
        return JsonResponse({"detail": "Non autorisé."}, status=401)
    return JsonResponse(run_weekly_import())
