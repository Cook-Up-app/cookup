"""Tâche hebdomadaire : découverte par source, puis import par lots."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.reference import RecipeSource

from .contracts import SearchQuery
from .exceptions import FetchFailed, FetchRefused, SourceUnavailable
from .importer import (
    already_known,
    build_source_for,
    enqueue_recipe,
    pending_recipe_jobs,
    process_pending,
)
from .models import ImportJob, SourceState
from .themes import themes_for_week

MIN_DAYS_BETWEEN_DISCOVERIES = 6
MARMITON = RecipeSource.MARMITON.value
MOULINEX = RecipeSource.MOULINEX.value


def _discovery_due(source_key: str, state: SourceState, now: datetime, quota: int) -> bool:
    recent = state.last_discovery_at and now - state.last_discovery_at < timedelta(
        days=MIN_DAYS_BETWEEN_DISCOVERIES
    )
    return not recent and pending_recipe_jobs(source_key).count() < quota


def _run_search(source, query: str, week: str, budget: int) -> int:
    job, _ = ImportJob.objects.get_or_create(
        source=MARMITON, kind=ImportJob.Kind.SEARCH, target=f"{query}|{week}"
    )
    if job.status == ImportJob.Status.DONE:
        return 0
    queued = 0
    try:
        for stub in source.search(SearchQuery(query)):
            if queued >= budget:
                break
            if not already_known(MARMITON, stub.url):
                queued += int(enqueue_recipe(MARMITON, stub.url)[1])
    except (FetchRefused, FetchFailed) as error:
        job.status, job.error = ImportJob.Status.FAILED, str(error)[:300]
    else:
        job.status = ImportJob.Status.DONE
    job.save(update_fields=["status", "error"])
    return queued


def discover(source, now: datetime) -> int:
    """Marmiton : une recherche par thème de la semaine, plafonné par le quota hebdomadaire."""
    year, week, _ = now.isocalendar()
    queued = 0
    for query in themes_for_week(week, settings.SOURCE_QUERIES_PER_WEEK):
        remaining = settings.SOURCE_IMPORT_WEEKLY_QUOTA - queued
        if remaining <= 0:
            break
        queued += _run_search(source, query, f"{year}-W{week:02d}", remaining)
    return queued


def discover_sitemap(source, now: datetime) -> int:
    """Moulinex : tirage hebdomadaire dans le sitemap (une seule requête, début du fichier)."""
    year, week, _ = now.isocalendar()
    quota = settings.SOURCE_MOULINEX_WEEKLY_QUOTA
    queued = 0
    for stub in source.discover(seed=year * 100 + week, limit=quota * 4):
        if queued >= quota:
            break
        if not already_known(MOULINEX, stub.url):
            queued += int(enqueue_recipe(MOULINEX, stub.url)[1])
    return queued


# Une stratégie de découverte par source : en ajouter une n'oblige pas à modifier le reste.
DISCOVERERS: dict[str, tuple[Callable, Callable[[], int]]] = {
    MARMITON: (discover, lambda: settings.SOURCE_IMPORT_WEEKLY_QUOTA),
    MOULINEX: (discover_sitemap, lambda: settings.SOURCE_MOULINEX_WEEKLY_QUOTA),
}


def enabled_sources() -> list[str]:
    flags = {MARMITON: settings.SOURCE_MARMITON_ENABLED, MOULINEX: settings.SOURCE_MOULINEX_ENABLED}
    return [key for key, enabled in flags.items() if enabled]


def _run_source(source_key: str, now: datetime) -> dict:
    source = build_source_for(source_key)
    state, _ = SourceState.objects.get_or_create(source=source_key)
    discoverer, quota = DISCOVERERS[source_key]
    discovered = 0
    try:
        if _discovery_due(source_key, state, now, quota()):
            discovered = discoverer(source, now)
            state.last_discovery_at = now
            state.save(update_fields=["last_discovery_at"])
        batch = process_pending(source_key, source, budget_seconds=settings.SOURCE_BATCH_SECONDS)
    except SourceUnavailable as error:
        return {"status": "paused", "detail": str(error)[:200]}
    return {"status": "ok", "discovered": discovered, **asdict(batch)}


def run_weekly_import(now: datetime | None = None) -> dict:
    """Appelée par le cron : pour chaque source activée, découvre si c'est l'heure puis importe.

    Le résultat agrège les sources (sommes) et détaille chacune sous `sources`.
    """
    keys = enabled_sources()
    if not keys:
        return {"status": "disabled"}
    now = now or timezone.now()
    per_source = {key: _run_source(key, now) for key in keys}
    ok = [r for r in per_source.values() if r["status"] == "ok"]
    total = {
        name: sum(r.get(name, 0) for r in ok)
        for name in ("discovered", "done", "skipped", "failed", "remaining")
    }
    stopped = ", ".join(r["stopped"] for r in ok if r.get("stopped"))
    status = "ok" if ok else "paused"
    return {"status": status, **total, "stopped": stopped, "sources": per_source}
