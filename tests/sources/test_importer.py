import pytest

from apps.catalog.models import Recipe
from apps.sources import importer
from apps.sources.adapters import MarmitonSource
from apps.sources.exceptions import SourceUnavailable
from apps.sources.http import RawResponse
from apps.sources.models import ImportJob
from tests.conftest import make_user
from tests.sources.conftest import html
from tests.sources.pages import recipe_page

BASE = "https://www.marmiton.org/recettes/recette_"


def _url(slug: str) -> str:
    return f"{BASE}{slug}.aspx"


@pytest.fixture
def run(make_fetcher, db):
    from apps.catalog.seeding import seed_ingredients
    from apps.catalog.services import load_index  # noqa: F401  (index rechargé à chaque import)

    seed_ingredients()

    def execute(pages):
        fetcher, transport = make_fetcher({_url(k): v for k, v in pages.items()})
        source = MarmitonSource(fetcher)
        job, _ = importer.enqueue_recipe("marmiton", _url(next(iter(pages))))
        return importer.run_recipe_job(job, source), transport

    return execute


def test_recipe_is_imported_and_normalised(run):
    job, _ = run({"gratin_1": html(recipe_page())})

    recipe = Recipe.objects.get()
    assert job.status == ImportJob.Status.DONE and job.recipe == recipe
    assert recipe.source == "marmiton" and recipe.url.endswith("gratin_1.aspx")
    assert recipe.ingredients.count() == 3
    assert recipe.ingredients.get(raw_text__startswith="20 cl").base_quantity == 200
    assert not recipe.needs_review


def test_same_recipe_twice_is_a_duplicate(run):
    run({"gratin_1": html(recipe_page())})

    job, _ = run({"gratin_2": html(recipe_page())})

    assert Recipe.objects.count() == 1
    assert job.status == ImportJob.Status.SKIPPED and job.error == "Déjà au catalogue."


def test_poorly_rated_recipe_is_skipped(run):
    job, _ = run({"gratin_1": html(recipe_page(rating=2.9))})

    assert job.status == ImportJob.Status.SKIPPED
    assert not Recipe.objects.exists()


def test_recipe_without_rating_is_kept(run):
    job, _ = run({"gratin_1": html(recipe_page(rating=None))})

    assert job.status == ImportJob.Status.DONE


def test_cookeo_recipes_are_flagged(run):
    run({"gratin_1": html(recipe_page(title="Gratin au Cookeo"))})

    assert Recipe.objects.get().cookeo_compatible is True


def test_unparsable_page_fails_for_good(run):
    job, _ = run({"x_1": html("<html>rien</html>")})

    assert job.status == ImportJob.Status.FAILED and job.error


def test_transient_failures_are_retried_then_abandoned(run, make_fetcher):
    failing = {_url("x_1"): RawResponse(500, {}, b"")}
    fetcher, _ = make_fetcher(failing)
    source = MarmitonSource(fetcher)
    job, _ = importer.enqueue_recipe("marmiton", _url("x_1"))

    statuses = [importer.run_recipe_job(job, source).status for _ in range(importer.MAX_ATTEMPTS)]

    assert statuses == ["pending", "pending", "failed"]


def test_blocked_source_stops_the_batch_and_keeps_jobs_pending(make_fetcher):
    fetcher, _ = make_fetcher({_url("a_1"): RawResponse(429, {"retry-after": "60"}, b"")})
    source = MarmitonSource(fetcher)
    for slug in ("a_1", "b_2"):
        importer.enqueue_recipe("marmiton", _url(slug))

    summary = importer.process_pending("marmiton", source, budget_seconds=30)

    assert summary.stopped == "source en pause"
    assert summary.remaining == 2
    assert ImportJob.objects.filter(status="pending").count() == 2


def test_batch_stops_when_the_time_budget_is_spent(make_fetcher):
    pages = {_url(f"r{i}_{i}"): html(recipe_page(title=f"Recette {i}")) for i in range(5)}
    urls = list(pages)  # make_fetcher ajoute robots.txt au dictionnaire
    fetcher, _ = make_fetcher(pages)
    source = MarmitonSource(fetcher)
    for url in urls:
        importer.enqueue_recipe("marmiton", url)
    ticks = iter(range(100))

    summary = importer.process_pending(
        "marmiton", source, budget_seconds=2.5, clock=lambda: float(next(ticks))
    )

    assert summary.stopped == "budget de temps atteint"
    assert summary.done + summary.skipped + summary.failed == 2
    assert summary.remaining == 3


def test_manual_enqueue_records_the_requester(db):
    user = make_user("a@example.com")

    job, created = importer.enqueue_recipe("url_import", "https://www.marmiton.org/x", user)
    again, created_again = importer.enqueue_recipe("url_import", "https://www.marmiton.org/x", user)

    assert created and not created_again and job == again and job.requested_by == user


def test_batch_with_blocked_source_raises_nothing_to_the_caller(make_fetcher):
    fetcher, _ = make_fetcher({_url("a_1"): RawResponse(503, {}, b"")})
    importer.enqueue_recipe("marmiton", _url("a_1"))

    with pytest.raises(SourceUnavailable):
        importer.run_recipe_job(ImportJob.objects.get(), MarmitonSource(fetcher))
