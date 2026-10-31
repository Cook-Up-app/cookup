import time

import pytest
from django.contrib.postgres.search import SearchVector
from django.urls import reverse

from apps.catalog.models import Recipe
from apps.catalog.services import SearchFilters, search_recipes

RECIPE_COUNT = 2000
BUDGET_SECONDS = 0.3  # SPEC section 12 : recherche en moins de 300 ms
MAX_QUERIES = 15

WORDS = [
    "poulet",
    "gratin",
    "courgette",
    "tomate",
    "riz",
    "saumon",
    "curry",
    "pomme",
    "chocolat",
    "lentille",
    "fromage",
    "soupe",
    "salade",
    "pâtes",
    "champignon",
    "carotte",
    "citron",
    "moutarde",
    "crème",
    "basilic",
]


@pytest.fixture
def big_catalogue(db):
    recipes = []
    for number in range(RECIPE_COUNT):
        words = [WORDS[(number * step) % len(WORDS)] for step in (1, 3, 7)]
        title = f"Recette {' '.join(words)} {number}"
        recipes.append(
            Recipe(
                source="manual",
                title=title,
                content_fingerprint=f"{number:064d}",
                search_text=f"{title} {words[0]}".lower(),
                prep_minutes=10 + number % 50,
            )
        )
    Recipe.objects.bulk_create(recipes, batch_size=500)
    Recipe.objects.update(search_vector=SearchVector("search_text", config="french"))


def test_search_stays_under_300_ms_on_two_thousand_recipes(big_catalogue):
    list(search_recipes(SearchFilters(query="poulet"))[:20])  # chauffe les plans

    started = time.perf_counter()
    for query in ("poulet", "gratin courgette", "poullet", "saumon curry"):
        list(search_recipes(SearchFilters(query=query, max_minutes=45))[:20])
    average = (time.perf_counter() - started) / 4

    assert average < BUDGET_SECONDS


def test_listing_page_stays_within_query_budget(
    owner_client, big_catalogue, django_assert_max_num_queries
):
    with django_assert_max_num_queries(MAX_QUERIES):
        assert owner_client.get(reverse("catalog:list"), {"q": "poulet"}).status_code == 200
