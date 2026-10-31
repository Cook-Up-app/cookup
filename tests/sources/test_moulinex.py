"""Adaptateur moulinex.fr : désactivé par défaut, découverte par sitemap, contenu minimal."""

from datetime import UTC, datetime

import pytest

from apps.catalog.models import Recipe
from apps.catalog.seeding import seed_ingredients
from apps.sources import importer, weekly
from apps.sources.adapters import MoulinexSource
from apps.sources.exceptions import FetchRefused, ParseFailed
from apps.sources.http import RawResponse
from apps.sources.models import ImportJob
from tests.sources.conftest import FakeTransport, html
from tests.sources.pages import recipe_page

HOST = "https://www.moulinex.fr"
SITEMAP = f"{HOST}/Recipe-fr_fr-EUR.xml"
NOW = datetime(2026, 11, 2, 4, 0, tzinfo=UTC)


def url(slug: str, number: int) -> str:
    return f"{HOST}/recette/detail/PRO/{slug}/{number}"


def sitemap(*urls: str) -> str:
    return "<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>"


def french(page: str) -> str:
    return page.replace("<html>", '<html lang="fr-FR">')


@pytest.fixture
def fetcher_for(clock, db):
    from apps.sources.http import PoliteFetcher
    from apps.sources.ratelimit import DatabaseRateLimiter
    from tests.sources.conftest import USER_AGENT

    def build(pages):
        transport = FakeTransport(pages)
        limiter = DatabaseRateLimiter("moulinex", sleep=clock.sleep, now=clock)
        fetcher = PoliteFetcher(
            user_agent=USER_AGENT,
            allowed_domains=frozenset({"moulinex.fr"}),
            limiter=limiter,
            transport=transport,
        )
        return fetcher, transport

    return build


def test_no_search_because_robots_txt_forbids_it(fetcher_for):
    fetcher, _ = fetcher_for({})

    assert not hasattr(MoulinexSource(fetcher), "search")
    assert hasattr(MoulinexSource(fetcher), "discover")


def test_discovery_samples_the_sitemap_reproducibly(fetcher_for):
    urls = [url(f"recette-{i}", 1000 + i) for i in range(40)]
    fetcher, transport = fetcher_for({SITEMAP: html(sitemap(*urls, f"{HOST}/produit/x/1"))})
    source = MoulinexSource(fetcher)

    first = source.discover(seed=202645, limit=5)
    again = source.discover(seed=202645, limit=5)
    other = source.discover(seed=202646, limit=5)

    assert first == again and first != other
    assert len(first) == 5 and all("/recette/detail/" in stub.url for stub in first)
    assert transport.requested.count(SITEMAP) == 3  # une requête par découverte


def test_only_recipe_pages_of_moulinex_can_be_fetched(fetcher_for):
    fetcher, _ = fetcher_for({})
    source = MoulinexSource(fetcher)

    for bad in (
        f"{HOST}/search?q=poulet",
        f"{HOST}/mon-compte",
        "https://autre.example/recette/detail/PRO/x/1",
    ):
        with pytest.raises(FetchRefused):
            source.fetch(bad)


def test_only_the_bare_minimum_is_kept(fetcher_for):
    page = french(
        recipe_page(title="Poulet basquaise au Cookeo", image="https://img.example/x.jpg")
    )
    fetcher, _ = fetcher_for({url("poulet", 1): html(page)})
    source = MoulinexSource(fetcher)

    dto = source.parse(source.fetch(url("poulet", 1)))

    assert dto.steps == [] and dto.image_url == ""
    assert dto.url == url("poulet", 1) and dto.ingredient_lines and dto.cookeo_compatible
    assert "moulinex" in dto.tags


def test_recipe_not_about_the_cookeo_is_not_flagged(fetcher_for):
    fetcher, _ = fetcher_for(
        {url("gateau", 2): html(french(recipe_page(title="Gâteau au yaourt")))}
    )
    source = MoulinexSource(fetcher)

    assert source.parse(source.fetch(url("gateau", 2))).cookeo_compatible is False


@pytest.mark.parametrize("lang", ['lang="nl-NL"', 'lang="en"', ""])
def test_non_french_pages_are_ignored(fetcher_for, lang):
    page = recipe_page().replace("<html>", f"<html {lang}>")
    fetcher, _ = fetcher_for({url("x", 3): html(page)})
    source = MoulinexSource(fetcher)

    with pytest.raises(ParseFailed):
        source.parse(source.fetch(url("x", 3)))


def test_total_time_alone_is_used_when_prep_and_cook_are_missing(fetcher_for):
    page = french(recipe_page()).replace('"prepTime": "PT15M", "cookTime": "PT30M", ', "")
    fetcher, _ = fetcher_for({url("x", 4): html(page)})
    source = MoulinexSource(fetcher)

    dto = source.parse(source.fetch(url("x", 4)))

    assert (dto.prep_minutes, dto.cook_minutes) == (45, None)


def test_disabled_by_default_and_domain_not_reachable(settings, db):
    settings.SOURCE_MARMITON_ENABLED = False
    settings.SOURCE_MOULINEX_ENABLED = False

    assert weekly.enabled_sources() == []
    assert weekly.run_weekly_import(NOW) == {"status": "disabled"}
    assert "moulinex.fr" not in settings.SOURCES_ALLOWED_DOMAINS


def test_moulinex_domain_is_only_allowed_when_the_source_is_enabled(monkeypatch):
    import importlib

    monkeypatch.setenv("SOURCE_MOULINEX_ENABLED", "true")
    monkeypatch.setenv("SECRET_KEY", "x" * 50)
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@localhost/db")
    from config.settings import base

    reloaded = importlib.reload(base)
    try:
        assert "moulinex.fr" in reloaded.SOURCES_ALLOWED_DOMAINS
    finally:
        monkeypatch.delenv("SOURCE_MOULINEX_ENABLED")
        importlib.reload(base)


@pytest.fixture
def wired(monkeypatch, fetcher_for, settings):
    seed_ingredients()
    settings.SOURCE_MOULINEX_ENABLED = True
    settings.SOURCE_MARMITON_ENABLED = False
    settings.SOURCE_MOULINEX_WEEKLY_QUOTA = 3
    settings.SOURCE_BATCH_SECONDS = 600

    def install(pages):
        fetcher, transport = fetcher_for(pages)
        monkeypatch.setattr(weekly, "build_source_for", lambda key: MoulinexSource(fetcher))
        return transport

    return install


def test_weekly_run_discovers_in_the_sitemap_then_imports(wired):
    urls = [url(f"recette-{i}", 100 + i) for i in range(12)]
    pages = {SITEMAP: html(sitemap(*urls))}
    pages.update({u: html(french(recipe_page(title=f"Cookeo n°{i}"))) for i, u in enumerate(urls)})
    wired(pages)

    result = weekly.run_weekly_import(NOW)

    assert result["status"] == "ok" and result["discovered"] == 3 and result["done"] == 3
    assert result["sources"]["moulinex"]["remaining"] == 0
    assert Recipe.objects.filter(source="moulinex").count() == 3
    assert all(
        r.steps == [] and r.cookeo_compatible for r in Recipe.objects.filter(source="moulinex")
    )


def test_known_pages_are_not_requested_twice(wired):
    only = url("seule", 1)
    transport = wired({SITEMAP: html(sitemap(only)), only: html(french(recipe_page()))})
    weekly.run_weekly_import(NOW)
    ImportJob.objects.filter(kind="recipe").update(status="done")
    from apps.sources.models import SourceState

    SourceState.objects.update(last_discovery_at=None)

    weekly.run_weekly_import(NOW)

    assert transport.requested.count(only) == 1


def test_a_blocked_sitemap_pauses_moulinex_only(wired):
    wired({SITEMAP: RawResponse(429, {"retry-after": "600"}, b"")})

    result = weekly.run_weekly_import(NOW)

    assert result["status"] == "paused" and result["sources"]["moulinex"]["status"] == "paused"


def test_importer_picks_the_moulinex_adapter_from_its_key(fetcher_for):
    fetcher, _ = fetcher_for({})

    from apps.sources.registry import build_source

    assert isinstance(build_source("moulinex", fetcher=fetcher), MoulinexSource)
    assert importer.source_key_for(url("x", 1)) == "url_import"
