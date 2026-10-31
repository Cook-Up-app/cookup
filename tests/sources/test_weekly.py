from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import pytest
from django.urls import reverse

from apps.catalog.models import Recipe
from apps.catalog.seeding import seed_ingredients
from apps.sources import weekly
from apps.sources.adapters import MarmitonSource
from apps.sources.http import RawResponse
from apps.sources.models import ImportJob, SourceState
from apps.sources.themes import DEFAULT_THEMES, themes_for_week
from tests.sources.conftest import html
from tests.sources.pages import recipe_page, search_page

NOW = datetime(2026, 11, 2, 4, 0, tzinfo=UTC)  # lundi, semaine 45
SEARCH = "https://www.marmiton.org/recettes/recherche.aspx?aqt={}"
RECIPE = "https://www.marmiton.org/recettes/recette_{}.aspx"


@pytest.fixture
def enabled(settings):
    settings.SOURCE_MARMITON_ENABLED = True
    settings.SOURCE_QUERIES_PER_WEEK = 2
    settings.SOURCE_IMPORT_WEEKLY_QUOTA = 3
    settings.SOURCE_BATCH_SECONDS = 600


@pytest.fixture
def wire(monkeypatch, make_fetcher, enabled):
    """Branche la tâche sur de fausses pages Marmiton (aucun accès réseau)."""
    seed_ingredients()

    def install(pages):
        fetcher, transport = make_fetcher(pages)
        monkeypatch.setattr(weekly, "build_source_for", lambda key: MarmitonSource(fetcher))
        return transport

    return install


def search_url(query: str) -> str:
    return SEARCH.format(quote(query))


def test_disabled_by_default_makes_no_request(settings, db):
    settings.SOURCE_MARMITON_ENABLED = False

    assert weekly.run_weekly_import(NOW) == {"status": "disabled"}
    assert not ImportJob.objects.exists()


def test_themes_rotate_and_wrap_around():
    assert themes_for_week(1, 4) != themes_for_week(2, 4)
    assert themes_for_week(0, 4) == list(DEFAULT_THEMES[:4])
    assert len(set(themes_for_week(len(DEFAULT_THEMES), 4))) == 4


def test_week_discovers_then_imports_everything_it_found(wire, enabled):
    first, second = themes_for_week(45, 2)
    pages = {
        search_url(first): html(search_page("a_1", "b_2")),
        search_url(second): html(search_page("c_3", "d_4")),
        **{
            RECIPE.format(slug): html(recipe_page(title=f"Recette {slug}"))
            for slug in ("a_1", "b_2", "c_3", "d_4")
        },
    }
    wire(pages)

    result = weekly.run_weekly_import(NOW)

    assert result["status"] == "ok"
    assert result["discovered"] == 3  # plafonné par le quota hebdomadaire
    assert result["done"] == 3 and result["remaining"] == 0
    assert Recipe.objects.count() == 3


def test_discovery_runs_at_most_once_per_week(wire, enabled):
    wire({})
    SourceState.objects.create(source="marmiton", last_discovery_at=NOW - timedelta(days=2))

    result = weekly.run_weekly_import(NOW)

    assert result["discovered"] == 0
    assert not ImportJob.objects.filter(kind="search").exists()


def test_discovery_is_due_again_after_six_days(wire, enabled):
    wire({})
    SourceState.objects.create(source="marmiton", last_discovery_at=NOW - timedelta(days=7))

    weekly.run_weekly_import(NOW)

    assert ImportJob.objects.filter(kind="search").count() == 2


def test_failing_searches_do_not_abort_the_task(wire, enabled):
    wire({})  # toute recherche répond 404

    result = weekly.run_weekly_import(NOW)

    assert result["status"] == "ok" and result["discovered"] == 0
    assert ImportJob.objects.filter(kind="search", status="failed").count() == 2


def test_known_recipes_are_not_requested_again(wire, enabled):
    next_week = NOW + timedelta(days=7)
    pages = {search_url(themes_for_week(week, 2)[0]): html(search_page("a_1")) for week in (45, 46)}
    pages[RECIPE.format("a_1")] = html(recipe_page())
    transport = wire(pages)
    weekly.run_weekly_import(NOW)

    weekly.run_weekly_import(next_week)

    assert transport.requested.count(RECIPE.format("a_1")) == 1


def test_blocked_source_pauses_the_whole_task(wire, enabled):
    first = themes_for_week(45, 2)[0]
    wire({search_url(first): RawResponse(429, {"retry-after": "3600"}, b"")})

    result = weekly.run_weekly_import(NOW)

    assert result["status"] == "paused"
    assert SourceState.objects.get(source="marmiton").cooldown_until is not None
    assert SourceState.objects.get(source="marmiton").last_discovery_at is None


@pytest.mark.django_db
def test_cron_import_endpoint_requires_the_secret(client, settings):
    settings.CRON_SECRET = "s" * 40

    assert client.get(reverse("core:cron-import")).status_code == 401
    assert (
        client.get(reverse("core:cron-import"), headers={"Authorization": "Bearer x"}).status_code
        == 401
    )


@pytest.mark.django_db
def test_cron_import_endpoint_reports_status(client, settings):
    settings.CRON_SECRET = "s" * 40
    settings.SOURCE_MARMITON_ENABLED = False

    response = client.get(
        reverse("core:cron-import"), headers={"Authorization": f"Bearer {'s' * 40}"}
    )

    assert response.status_code == 200 and response.json() == {"status": "disabled"}
