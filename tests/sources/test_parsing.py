import pytest

from apps.sources.exceptions import ParseFailed
from apps.sources.parsing import clean_text, parse_recipe_html
from tests.sources.pages import recipe_page

URL = "https://www.marmiton.org/recettes/recette_gratin-de-courgettes_1234.aspx"


def test_json_ld_recipe_is_extracted():
    dto = parse_recipe_html(recipe_page(), URL, "marmiton")

    assert dto.title == "Gratin de courgettes"
    assert dto.ingredient_lines == [
        "3 courgettes",
        "20 cl de crème liquide",
        "100 g de gruyère râpé",
    ]
    assert dto.steps == ["Couper les courgettes.", "Enfourner 30 minutes."]
    assert (dto.servings, dto.prep_minutes, dto.cook_minutes) == (4, 15, 30)
    assert dto.rating == pytest.approx(4.6)
    assert dto.source_ref == "www.marmiton.org/recettes/recette_gratin-de-courgettes_1234.aspx"
    assert dto.meal_types == ["lunch", "dinner"]
    assert "gratin" in dto.tags


def test_dessert_category_sets_meal_type():
    dto = parse_recipe_html(recipe_page(category="Dessert"), URL, "marmiton")

    assert dto.meal_types == ["dessert"]


def test_html_from_the_source_is_stripped():
    page = recipe_page(
        title="Tarte <script>alert(1)</script><b>aux</b> pommes &amp; poires",
        steps=("Étaler <img src=x onerror=alert(1)> la pâte.",),
    )

    dto = parse_recipe_html(page, URL, "marmiton")

    assert "<" not in dto.title and "script" not in dto.title.replace("alert", "")
    assert "&amp;" not in dto.title and "pommes & poires" in dto.title
    assert "<" not in dto.steps[0] and "onerror" not in dto.steps[0]


@pytest.mark.parametrize("image", ["javascript:alert(1)", "data:text/html,x", "ftp://x/y.jpg"])
def test_non_http_images_are_dropped(image):
    assert parse_recipe_html(recipe_page(image=image), URL, "marmiton").image_url == ""


def test_absurd_servings_fall_back_to_default():
    assert parse_recipe_html(recipe_page(servings="9999"), URL, "marmiton").servings == 4


@pytest.mark.parametrize("page", ["<html><body>pas de recette</body></html>", "", "<script>"])
def test_pages_without_a_recipe_are_rejected(page):
    with pytest.raises(ParseFailed):
        parse_recipe_html(page, URL, "marmiton")


def test_recipe_without_ingredients_is_rejected():
    with pytest.raises(ParseFailed):
        parse_recipe_html(recipe_page(ingredients=()), URL, "marmiton")


def test_clean_text_removes_markup_and_decodes_entities():
    assert clean_text("<p>a &amp; <i>b</i></p>") == "a & b"
