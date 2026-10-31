import pytest
from django.core.management import call_command

from apps.catalog.models import Ingredient, Recipe, RecipeIngredient
from apps.catalog.starter import starter_recipes

ACCEPTANCE_RATE = 0.95  # SPEC section 12, M2 : ingrédients normalisés automatiquement


@pytest.fixture
def seeded(db):
    call_command("seed_catalog", verbosity=0)


def test_starter_set_is_about_eighty_with_a_third_for_the_cookeo():
    recipes = starter_recipes()

    assert 80 <= len(recipes) <= 90
    assert sum(r.cookeo_compatible for r in recipes) >= 30


def test_every_starter_recipe_is_complete():
    for recipe in starter_recipes():
        assert recipe.ingredient_lines, recipe.title
        assert len(recipe.steps) >= 2, recipe.title
        assert recipe.servings > 0 and recipe.meal_types, recipe.title
        if recipe.cookeo_compatible:
            assert recipe.cookeo_program["pressure_minutes"] > 0, recipe.title
            assert recipe.servings <= 6, recipe.title  # cuve de 6 L


def test_loading_creates_the_catalogue_and_is_idempotent(seeded):
    first = Recipe.objects.count()
    call_command("seed_catalog", verbosity=0)

    assert first == len(starter_recipes())
    assert Recipe.objects.count() == first
    assert Ingredient.objects.count() > 200
    assert Recipe.objects.filter(cookeo_compatible=True).count() >= 30


@pytest.mark.django_db
def test_at_least_95_percent_of_ingredients_are_normalised_automatically(seeded):
    lines = RecipeIngredient.objects.all()
    total = lines.count()
    reviewed = (
        lines.filter(needs_review=True).count() + lines.filter(ingredient__isnull=True).count()
    )
    unmatched = list(
        lines.filter(ingredient__isnull=True).values_list("raw_text", flat=True)
    ) + list(lines.filter(needs_review=True).values_list("raw_text", flat=True))

    assert 1 - reviewed / total >= ACCEPTANCE_RATE, unmatched


@pytest.mark.django_db
def test_cookeo_recipes_require_the_cookeo_equipment(seeded):
    recipe = Recipe.objects.filter(cookeo_compatible=True).first()

    assert recipe.equipment.filter(equipment_id="cookeo_yy5449fb", required=True).exists()
