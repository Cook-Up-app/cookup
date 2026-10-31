"""File d'import : un import = une recette = une requête ; reprise sûre en cas d'arrêt."""

import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from django.conf import settings
from django.utils import timezone

from apps.catalog.models import Recipe
from apps.catalog.services import load_index, save_recipe
from apps.catalog.text import fold
from apps.core.reference import RecipeSource

from .adapters import MARMITON_HOST
from .exceptions import FetchFailed, FetchRefused, ParseFailed, SourceUnavailable
from .http import PoliteFetcher
from .models import ImportJob
from .parsing import source_ref_of
from .ratelimit import DatabaseRateLimiter
from .registry import build_source

MAX_ATTEMPTS = 3
MIN_RATING = 3.8  # en dessous, la recette n'est pas importée automatiquement
ERROR_LENGTH = 300


def build_fetcher(source_key: str) -> PoliteFetcher:
    return PoliteFetcher(
        user_agent=settings.SOURCES_USER_AGENT,
        allowed_domains=settings.SOURCES_ALLOWED_DOMAINS,
        limiter=DatabaseRateLimiter(source_key),
    )


def source_key_for(url: str) -> str:
    return RecipeSource.MARMITON.value if MARMITON_HOST in url else RecipeSource.URL_IMPORT.value


def enqueue_recipe(source: str, url: str, requested_by=None) -> tuple[ImportJob, bool]:
    return ImportJob.objects.get_or_create(
        source=source,
        kind=ImportJob.Kind.RECIPE,
        target=url[:500],
        defaults={"requested_by": requested_by},
    )


def already_known(source: str, url: str) -> bool:
    """Recette déjà au catalogue ou déjà en file : inutile de la redemander."""
    ref = source_ref_of(url)
    return (
        Recipe.objects.filter(source=source, source_ref=ref).exists()
        or ImportJob.objects.filter(source=source, kind=ImportJob.Kind.RECIPE, target=url).exists()
    )


def _finish(
    job: ImportJob, status: str, error: str = "", recipe: Recipe | None = None
) -> ImportJob:
    job.status = status
    job.error = error[:ERROR_LENGTH]
    job.recipe = recipe
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error", "recipe", "finished_at"])
    return job


def _with_cookeo_flag(dto):
    text = fold(" ".join([dto.title, *dto.tags]))
    return replace(dto, cookeo_compatible=True) if "cookeo" in text else dto


def run_recipe_job(job: ImportJob, source) -> ImportJob:
    """Exécute un import ; les erreurs définitives ne sont pas rejouées, les transitoires oui."""
    job.attempts += 1
    job.status = ImportJob.Status.RUNNING
    job.save(update_fields=["attempts", "status"])
    try:
        dto = source.parse(source.fetch(job.target))
    except (FetchRefused, ParseFailed) as error:
        return _finish(job, ImportJob.Status.FAILED, str(error))
    except FetchFailed as error:
        retry = job.attempts < MAX_ATTEMPTS
        status = ImportJob.Status.PENDING if retry else ImportJob.Status.FAILED
        return _finish(job, status, str(error))
    except SourceUnavailable:
        job.status = ImportJob.Status.PENDING
        job.attempts -= 1
        job.save(update_fields=["status", "attempts"])
        raise
    if dto.rating is not None and dto.rating < MIN_RATING:
        return _finish(job, ImportJob.Status.SKIPPED, "Note trop faible.")
    recipe, created = save_recipe(_with_cookeo_flag(dto), load_index())
    note = "" if created else "Déjà au catalogue."
    return _finish(
        job, ImportJob.Status.DONE if created else ImportJob.Status.SKIPPED, note, recipe
    )


@dataclass
class BatchSummary:
    done: int = 0
    skipped: int = 0
    failed: int = 0
    remaining: int = 0
    stopped: str = ""


def pending_recipe_jobs(source: str):
    return ImportJob.objects.filter(
        source=source, kind=ImportJob.Kind.RECIPE, status=ImportJob.Status.PENDING
    ).order_by("created_at")


def process_pending(
    source_key: str,
    source,
    *,
    budget_seconds: float,
    clock: Callable[[], float] = time.monotonic,
) -> BatchSummary:
    """Traite les imports en attente jusqu'à épuisement du temps (une invocation = un lot)."""
    summary = BatchSummary()
    deadline = clock() + budget_seconds
    for job in pending_recipe_jobs(source_key)[:200]:
        if clock() >= deadline:
            summary.stopped = "budget de temps atteint"
            break
        try:
            finished = run_recipe_job(job, source)
        except SourceUnavailable:
            summary.stopped = "source en pause"
            break
        counts = {"done": "done", "skipped": "skipped", "failed": "failed"}
        if finished.status in counts:
            setattr(summary, counts[finished.status], getattr(summary, counts[finished.status]) + 1)
    summary.remaining = pending_recipe_jobs(source_key).count()
    return summary


def build_source_for(source_key: str):
    return build_source(source_key, fetcher=build_fetcher(source_key))
