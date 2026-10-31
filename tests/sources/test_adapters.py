"""Suite de contrat : toute source se comporte pareil (Liskov) ; la recherche est un plus."""

import pytest

from apps.catalog.dto import RecipeDTO
from apps.sources.adapters import MarmitonSource, UrlImportSource
from apps.sources.contracts import RawRecipe, SearchQuery
from apps.sources.exceptions import FetchRefused
from apps.sources.registry import build_source, registered_keys
from tests.sources.conftest import html
from tests.sources.pages import recipe_page, search_page

RECIPE = "https://www.marmiton.org/recettes/recette_gratin-de-courgettes_1234.aspx"
SEARCH = "https://www.marmiton.org/recettes/recherche.aspx?aqt=gratin"


@pytest.fixture(params=["url_import", "marmiton"])
def source(request, make_fetcher):
    fetcher, _ = make_fetcher({RECIPE: html(recipe_page())})
    return build_source(request.param, fetcher=fetcher)


@pytest.mark.django_db
def test_every_source_fetches_then_parses(source):
    raw = source.fetch(RECIPE)
    dto = source.parse(raw)

    assert isinstance(raw, RawRecipe)
    assert isinstance(dto, RecipeDTO)
    assert dto.source == source.key
    assert dto.ingredient_lines and dto.steps and dto.title


def test_sources_are_registered():
    assert {"url_import", "marmiton"} <= set(registered_keys())


@pytest.mark.django_db
def test_only_marmiton_can_search(make_fetcher):
    fetcher, _ = make_fetcher()

    assert not hasattr(UrlImportSource(fetcher), "search")
    assert hasattr(MarmitonSource(fetcher), "search")


@pytest.mark.django_db
def test_marmiton_search_asks_for_the_first_page_only(make_fetcher):
    fetcher, transport = make_fetcher(
        {SEARCH: html(search_page("gratin-a_1.aspx".replace(".aspx", ""), "gratin-b_2"))}
    )

    stubs = MarmitonSource(fetcher).search(SearchQuery("gratin"))

    assert [stub.url for stub in stubs] == [
        "https://www.marmiton.org/recettes/recette_gratin-a_1.aspx",
        "https://www.marmiton.org/recettes/recette_gratin-b_2.aspx",
    ]
    assert transport.requested[-1] == SEARCH
    assert all("page=" not in url and "start=" not in url for url in transport.requested)


@pytest.mark.django_db
def test_marmiton_search_encodes_the_query_and_ignores_other_links(make_fetcher):
    url = "https://www.marmiton.org/recettes/recherche.aspx?aqt=p%C3%A2tes%20%26%20riz"
    fetcher, _ = make_fetcher({url: html(search_page("pates_9"))})

    stubs = MarmitonSource(fetcher).search(SearchQuery("pâtes & riz"))

    assert len(stubs) == 1


@pytest.mark.django_db
def test_marmiton_search_without_results_returns_nothing(make_fetcher):
    fetcher, _ = make_fetcher({SEARCH: html("<html>changement de format</html>")})

    assert MarmitonSource(fetcher).search(SearchQuery("gratin")) == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url",
    [
        "https://www.marmiton.org/mon-espace/profil",
        "https://www.marmiton.org/recettes/recherche.aspx?aqt=x",
        "https://www.marmiton.org/forum/x",
    ],
)
def test_marmiton_only_fetches_recipe_pages(make_fetcher, url):
    fetcher, _ = make_fetcher({url: html()})

    with pytest.raises(FetchRefused):
        MarmitonSource(fetcher).fetch(url)
