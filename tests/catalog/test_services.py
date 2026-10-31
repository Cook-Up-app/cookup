import pytest

from apps.catalog.dto import RecipeDTO
from apps.catalog.models import Recipe
from apps.catalog.seeding import seed_ingredients
from apps.catalog.services import SearchFilters, recipe_allergens, save_recipe, search_recipes


@pytest.fixture(autouse=True)
def catalogue(db):
    seed_ingredients()


def dto(title="Gratin de courgettes", lines=None, **kwargs) -> RecipeDTO:
    kwargs.setdefault("meal_types", ["lunch", "dinner"])
    return RecipeDTO(
        source="manual",
        title=title,
        ingredient_lines=lines
        or ["3 courgettes", "20 cl de crème liquide", "100 g de gruyère râpé"],
        steps=["Cuire."],
        **kwargs,
    )


def test_ingredients_are_normalised_and_converted():
    recipe, created = save_recipe(dto())

    cream = recipe.ingredients.get(raw_text__startswith="20 cl")
    assert created
    assert (cream.quantity, cream.unit, cream.base_quantity, cream.base_unit) == (
        20,
        "cl",
        200,
        "ml",
    )
    assert cream.ingredient.name == "crème liquide"
    assert recipe.ingredients.get(raw_text__startswith="3 ").base_unit == "pièce"


def test_raw_text_is_always_kept_for_later_renormalisation():
    recipe, _ = save_recipe(dto(lines=["2 c. à soupe d'huile d'olive"]))

    assert recipe.ingredients.get().raw_text == "2 c. à soupe d'huile d'olive"


def test_unknown_ingredient_is_flagged_and_not_guessed():
    recipe, _ = save_recipe(dto(lines=["2 pierres de lune", "3 courgettes"]))

    unknown = recipe.ingredients.get(raw_text__contains="lune")
    assert unknown.ingredient is None and unknown.needs_review
    assert recipe.needs_review


def test_partial_match_is_flagged_for_review():
    recipe, _ = save_recipe(dto(lines=["100 g de beurre de karité"]))

    assert recipe.ingredients.get().needs_review


def test_duplicates_are_detected_by_content_fingerprint():
    first, _ = save_recipe(dto())
    second, created = save_recipe(dto(title="  GRATIN de courgettes "))

    assert not created and second == first and Recipe.objects.count() == 1


def test_duplicates_are_detected_by_source_reference():
    first, _ = save_recipe(dto(source_ref="x/1", url="https://example.test/1"))
    second, created = save_recipe(dto(title="Autre titre", lines=["1 pomme"], source_ref="x/1"))

    assert not created and second == first


def test_compound_line_creates_two_ingredients():
    recipe, _ = save_recipe(dto(lines=["Sel, poivre"]))

    assert recipe.ingredients.count() == 2


def test_allergens_come_from_recognised_ingredients():
    recipe, _ = save_recipe(dto(lines=["3 œufs", "100 g de farine", "1 pincée de sel"]))

    allergens, uncertain = recipe_allergens(
        Recipe.objects.prefetch_related("ingredients__ingredient").get(pk=recipe.pk)
    )

    assert allergens == ["eggs", "gluten"] and not uncertain


def test_unreviewed_or_unknown_ingredients_make_allergens_uncertain():
    recipe, _ = save_recipe(dto(lines=["4 saucisses"]))

    _, uncertain = recipe_allergens(
        Recipe.objects.prefetch_related("ingredients__ingredient").get(pk=recipe.pk)
    )

    assert uncertain


@pytest.fixture
def library():
    save_recipe(
        dto(
            "Poulet rôti aux herbes",
            ["1 poulet entier", "2 c. à soupe d'huile d'olive"],
            prep_minutes=15,
            cook_minutes=60,
        )
    )
    save_recipe(
        dto(
            "Crème brûlée",
            ["20 cl de crème liquide", "3 œufs"],
            prep_minutes=10,
            cook_minutes=40,
            meal_types=["dessert"],
        )
    )
    save_recipe(
        dto(
            "Salade de tomates",
            ["4 tomates", "1 c. à soupe de basilic"],
            prep_minutes=10,
            tags=["été"],
        )
    )


def titles(**filters) -> list[str]:
    return [r.title for r in search_recipes(SearchFilters(**filters))]


def test_search_ignores_accents_and_case(library):
    assert titles(query="CREME brulee") == ["Crème brûlée"]
    assert titles(query="rôti") == ["Poulet rôti aux herbes"]


def test_search_finds_ingredients(library):
    assert "Poulet rôti aux herbes" in titles(query="poulet")
    assert "Crème brûlée" in titles(query="œufs")


def test_search_uses_french_stemming(library):
    assert titles(query="tomate") == ["Salade de tomates"]


def test_search_tolerates_typos(library):
    assert titles(query="poullet") == ["Poulet rôti aux herbes"]


def test_filters(library):
    assert titles(meal_type="dessert") == ["Crème brûlée"]
    assert titles(max_minutes=20) == ["Salade de tomates"]
    assert set(titles(max_minutes=60)) == {"Crème brûlée", "Salade de tomates"}
    assert titles(source="starter") == []
    assert titles(tag="été") == ["Salade de tomates"]


def test_empty_search_lists_everything(library):
    assert len(titles()) == 3
