import pytest
from django.urls import reverse

from apps.catalog.models import Recipe
from apps.catalog.seeding import seed_ingredients
from apps.catalog.services import save_recipe
from apps.sources.contracts import RawRecipe
from apps.sources.exceptions import SourceUnavailable
from apps.sources.models import ImportJob
from apps.sources.parsing import parse_recipe_html
from tests.catalog.test_services import dto
from tests.conftest import make_user
from tests.sources.pages import recipe_page

URL = "https://www.marmiton.org/recettes/recette_gratin_1.aspx"


class StubSource:
    """Source sans réseau : renvoie une page fabriquée."""

    def __init__(self, page: str) -> None:
        self.page = page

    def fetch(self, ref: str) -> RawRecipe:
        return RawRecipe(ref, self.page)

    def parse(self, raw: RawRecipe):
        return parse_recipe_html(raw.html, raw.url, "marmiton")


@pytest.fixture
def recipe(db):
    seed_ingredients()
    return save_recipe(dto(source_ref="x/1", url="https://example.test/1"))[0]


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["catalog:list", "catalog:import", "catalog:create"])
def test_catalogue_pages_require_a_session(client, name):
    assert client.get(reverse(name)).status_code == 302


@pytest.mark.django_db
def test_simple_member_can_browse_the_catalogue(client, recipe):
    owner = make_user("boss@example.com")
    from apps.households import services
    from apps.households.models import Membership

    services.create_household(owner, "Foyer")
    member = make_user("member@example.com", mfa=False)
    Membership.objects.create(user=member, household=Membership.objects.get().household)
    client.force_login(member)

    assert client.get(reverse("catalog:list")).status_code == 200
    assert client.get(reverse("catalog:detail", args=[recipe.pk])).status_code == 200


def test_list_and_search(owner_client, recipe):
    page = owner_client.get(reverse("catalog:list"), {"q": "courgette"}).content.decode()

    assert "Gratin de courgettes" in page
    assert (
        "Aucune recette"
        in owner_client.get(reverse("catalog:list"), {"q": "zzzz"}).content.decode()
    )


def test_detail_shows_source_link_and_allergen_disclaimer(owner_client, recipe):
    page = owner_client.get(reverse("catalog:detail", args=[recipe.pk])).content.decode()

    assert 'href="https://example.test/1"' in page and "noopener" in page
    assert "Allergènes détectés" in page and "garantie médicale" in page


def test_stored_text_is_escaped_in_pages(owner_client, db):
    seed_ingredients()
    evil, _ = save_recipe(dto(title="<script>alert(1)</script>", lines=["1 <img src=x onerror=y>"]))

    page = owner_client.get(reverse("catalog:detail", args=[evil.pk])).content.decode()

    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page


def test_manual_recipe_creation(owner_client, db):
    seed_ingredients()
    response = owner_client.post(
        reverse("catalog:create"),
        {
            "title": "Œufs mimosa",
            "servings": 4,
            "meal_types": ["lunch"],
            "tags": "entrée, œufs",
            "ingredients": "4 œufs\n1 c. à soupe de mayonnaise",
            "steps": "Cuire les œufs.\nGarnir.",
        },
    )

    recipe = Recipe.objects.get(title="Œufs mimosa")
    assert response.status_code == 302
    assert (
        recipe.source == "manual"
        and recipe.ingredients.count() == 2
        and recipe.steps == ["Cuire les œufs.", "Garnir."]
    )


def test_manual_recipe_needs_ingredients(owner_client, db):
    response = owner_client.post(
        reverse("catalog:create"),
        {
            "title": "Vide",
            "servings": 4,
            "meal_types": ["lunch"],
            "ingredients": "  ",
            "steps": "x",
        },
    )

    assert response.status_code == 200 and not Recipe.objects.exists()


def test_import_by_url_creates_the_recipe(owner_client, monkeypatch, db):
    seed_ingredients()
    monkeypatch.setattr(
        "apps.catalog.views.build_source_for", lambda key: StubSource(recipe_page())
    )

    response = owner_client.post(reverse("catalog:import"), {"url": URL})

    recipe = Recipe.objects.get()
    assert response.status_code == 302 and response["Location"] == reverse(
        "catalog:detail", args=[recipe.pk]
    )
    assert ImportJob.objects.get().requested_by.email == "owner@example.com"


def test_import_reports_an_unavailable_source(owner_client, monkeypatch, db):
    def unavailable(key):
        raise SourceUnavailable("Source en pause.")

    monkeypatch.setattr("apps.catalog.views.build_source_for", unavailable)

    response = owner_client.post(reverse("catalog:import"), {"url": URL}, follow=True)

    assert "Source indisponible" in response.content.decode() and not Recipe.objects.exists()


def test_import_is_rate_limited_per_user(owner_client, owner, monkeypatch, db):
    monkeypatch.setattr(
        "apps.catalog.views.build_source_for", lambda key: StubSource(recipe_page())
    )
    for index in range(20):
        ImportJob.objects.create(
            source="url_import", target=f"https://www.marmiton.org/{index}", requested_by=owner
        )

    response = owner_client.post(reverse("catalog:import"), {"url": URL}, follow=True)

    assert "imports récents" in response.content.decode() and not Recipe.objects.exists()


def test_import_rejects_invalid_urls(owner_client, db):
    response = owner_client.post(reverse("catalog:import"), {"url": "pas une url"})

    assert response.status_code == 200 and not ImportJob.objects.exists()
