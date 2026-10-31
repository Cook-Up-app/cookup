"""Tâche hebdomadaire : découverte par recherches thématiques, puis import par lots."""

from dataclasses import asdict
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.reference import RecipeSource

from .contracts import SearchQuery
from .exceptions import FetchFailed, FetchRefused, SourceUnavailable
from .importer import (
    BatchSummary,
    already_known,
    build_source_for,
    enqueue_recipe,
    pending_recipe_jobs,
    process_pending,
)
from .models import ImportJob, SourceState
from .themes import themes_for_week

MIN_DAYS_BETWEEN_DISCOVERIES = 6
SOURCE = RecipeSource.MARMITON.value


def _discovery_due(state: SourceState, now: datetime, quota: int) -> bool:
    recent = state.last_discovery_at and now - state.last_discovery_at < timedelta(
        days=MIN_DAYS_BETWEEN_DISCOVERIES
    )
    return not recent and pending_recipe_jobs(SOURCE).count() < quota


def _run_search(source, query: str, week: str, budget: int) -> int:
    job, _ = ImportJob.objects.get_or_create(
        source=SOURCE, kind=ImportJob.Kind.SEARCH, target=f"{query}|{week}"
    )
    if job.status == ImportJob.Status.DONE:
        return 0
    queued = 0
    try:
        for stub in source.search(SearchQuery(query)):
            if queued >= budget:
                break
            if not already_known(SOURCE, stub.url):
                queued += int(enqueue_recipe(SOURCE, stub.url)[1])
    except (FetchRefused, FetchFailed) as error:
        job.status, job.error = ImportJob.Status.FAILED, str(error)[:300]
    else:
        job.status = ImportJob.Status.DONE
    job.save(update_fields=["status", "error"])
    return queued


def discover(source, now: datetime) -> int:
    """Une requête de recherche par thème de la semaine ; plafonné par le quota hebdomadaire."""
    year, week, _ = now.isocalendar()
    queued = 0
    for query in themes_for_week(week, settings.SOURCE_QUERIES_PER_WEEK):
        remaining = settings.SOURCE_IMPORT_WEEKLY_QUOTA - queued
        if remaining <= 0:
            break
        queued += _run_search(source, query, f"{year}-W{week:02d}", remaining)
    return queued


def run_weekly_import(now: datetime | None = None) -> dict:
    """Appelée par le cron : découvre si c'est l'heure, puis traite un lot d'imports."""
    if not settings.SOURCE_MARMITON_ENABLED:
        return {"status": "disabled"}
    now = now or timezone.now()
    source = build_source_for(SOURCE)
    state, _ = SourceState.objects.get_or_create(source=SOURCE)
    discovered = 0
    try:
        if _discovery_due(state, now, settings.SOURCE_IMPORT_WEEKLY_QUOTA):
            discovered = discover(source, now)
            state.last_discovery_at = now
            state.save(update_fields=["last_discovery_at"])
        batch = process_pending(SOURCE, source, budget_seconds=settings.SOURCE_BATCH_SECONDS)
    except SourceUnavailable as error:
        return {"status": "paused", "detail": str(error)[:200]}
    return {"status": "ok", "discovered": discovered, **asdict(batch)}


__all__ = ["BatchSummary", "discover", "run_weekly_import"]
