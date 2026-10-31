import hmac
import json
from http import HTTPStatus

from django.conf import settings
from django.db import Error as DatabaseError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.http import require_GET, require_safe

from apps.households.permissions import household_required
from apps.onboarding import services as onboarding
from apps.planner import dashboard
from apps.sources.weekly import run_weekly_import

from . import services

BEARER_PREFIX = "Bearer "
SHELL_ASSETS = (
    "css/tokens.css",
    "css/base.css",
    "css/layout.css",
    "css/components.css",
    "js/outbox.js",
    "js/offline.js",
    "js/ui.js",
    "js/durations.js",
    "js/kitchen.js",
    "js/export.js",
    "icons/icon-192.png",
)


@require_safe
@household_required
def home(request: HttpRequest) -> HttpResponse:
    """Accueil : les repas du jour, les courses restantes, et le prochain geste utile."""
    if request.membership.is_owner and onboarding.needs_onboarding(request.household):
        return redirect("onboarding:start")
    today = timezone.localdate()
    context = {
        "today_date": today,
        "household": request.household,
        **dashboard.build(request.household, today),
    }
    return render(request, "home.html", context)


@require_safe
def more(request: HttpRequest) -> HttpResponse:
    """Page « Plus » : tout ce qui ne tient pas dans la barre du bas."""
    return render(request, "more.html")


@require_safe
def manifest(request: HttpRequest) -> HttpResponse:
    return render(request, "pwa/manifest.webmanifest", content_type="application/manifest+json")


@require_safe
def offline(request: HttpRequest) -> HttpResponse:
    return render(request, "pwa/offline.html")


@require_safe
def service_worker(request: HttpRequest) -> HttpResponse:
    """Servi à la racine pour que sa portée couvre tout le site (pas sous /static/)."""
    shell = ["/hors-ligne", "/manifest.webmanifest", *(static(p) for p in SHELL_ASSETS)]
    response = render(
        request,
        "pwa/sw.js",
        {"version": settings.APP_VERSION, "shell_urls": json.dumps(shell)},
        content_type="text/javascript; charset=utf-8",
    )
    response.headers["Cache-Control"] = "no-cache"  # le navigateur revérifie à chaque démarrage
    response.headers["Service-Worker-Allowed"] = "/"
    return response


def too_many_requests(request: HttpRequest) -> HttpResponse:
    """Réponse de la limitation de débit (allauth la cherche dans `handler429` de l'urlconf)."""
    return render(request, "429.html", status=HTTPStatus.TOO_MANY_REQUESTS)


@require_safe
def health(request: HttpRequest) -> JsonResponse:
    """État de l'application, sans donnée sensible."""
    try:
        services.check_database()
    except DatabaseError:
        return JsonResponse({"status": "degraded", "database": "down"}, status=503)
    return JsonResponse(
        {"status": "ok", "database": "up", "keepalive": services.keepalive_status()}
    )


def _is_authorized_cron(request: HttpRequest) -> bool:
    expected = settings.CRON_SECRET
    header = request.headers.get("Authorization", "")
    if not expected or not header.startswith(BEARER_PREFIX):
        return False
    return hmac.compare_digest(header[len(BEARER_PREFIX) :], expected)


@require_GET
def cron_daily(request: HttpRequest) -> JsonResponse:
    """Tâche quotidienne Vercel Cron : maintien de la base active, purges."""
    if not _is_authorized_cron(request):
        return JsonResponse({"detail": "Non autorisé."}, status=401)
    try:
        report = services.run_daily_maintenance()
    except DatabaseError:
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok", "purged_invitations": report["purged_invitations"]})


@require_GET
def cron_import(request: HttpRequest) -> JsonResponse:
    """Import hebdomadaire de recettes (Vercel Cron) ; peut être rappelé pour vider la file."""
    if not _is_authorized_cron(request):
        return JsonResponse({"detail": "Non autorisé."}, status=401)
    return JsonResponse(run_weekly_import())
