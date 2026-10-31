"""Chargement des recettes originales du jeu de départ (rédigées pour le projet).

Format d'un bloc de `starter_data.RECIPES` :
    ## Titre | portions | préparation | cuisson | repas | équipements | étiquettes
    + ingrédient          (une ligne par ingrédient)
    - étape               (une ligne par étape)
    @ mode | minutes [| crisp]   (Cookeo : programme, durée sous pression, couvercle Extra Crisp)
Repas : b petit-déjeuner, l déjeuner, d dîner, s collation, x dessert.
Équipements (obligatoires) : c Cookeo, o four, h plaques, m micro-ondes, b mixeur, r robot,
d cocotte.
"""

from apps.core.reference import Equipment, MealType, RecipeSource

from .dto import RecipeDTO
from .models import Recipe
from .services import load_index, save_recipe
from .starter_data import RECIPES

MEALS = {
    "b": MealType.BREAKFAST,
    "l": MealType.LUNCH,
    "d": MealType.DINNER,
    "s": MealType.SNACK,
    "x": MealType.DESSERT,
}
EQUIPMENT = {
    "c": Equipment.COOKEO,
    "o": Equipment.OVEN,
    "h": Equipment.HOB,
    "m": Equipment.MICROWAVE,
    "b": Equipment.BLENDER,
    "r": Equipment.FOOD_PROCESSOR,
    "d": Equipment.DUTCH_OVEN,
}
HEADER_FIELDS = 7


def _codes(field: str) -> list[str]:
    return [code.strip() for code in field.split(",") if code.strip()]


def _minutes(value: str) -> int | None:
    return int(value) if value.strip() else None


def parse_block(block: str) -> RecipeDTO:
    lines = [line.rstrip() for line in block.strip().splitlines() if line.strip()]
    header = [part.strip() for part in lines[0].removeprefix("##").split("|")]
    if len(header) != HEADER_FIELDS:
        raise ValueError(f"En-tête invalide : {lines[0]}")
    title, servings, prep, cook, meals, equipment, tags = header
    ingredients = [line[1:].strip() for line in lines[1:] if line.startswith("+")]
    steps = [line[1:].strip() for line in lines[1:] if line.startswith("-")]
    program = {}
    for line in lines[1:]:
        if line.startswith("@"):
            mode, minutes, *options = (part.strip() for part in line[1:].split("|"))
            program = {
                "mode": mode,
                "pressure_minutes": int(minutes),
                "extra_crisp": "crisp" in options,
            }
    required = [EQUIPMENT[code].value for code in _codes(equipment)]
    return RecipeDTO(
        source=RecipeSource.STARTER.value,
        title=title,
        ingredient_lines=ingredients,
        steps=steps,
        servings=int(servings),
        prep_minutes=_minutes(prep),
        cook_minutes=_minutes(cook),
        tags=[tag.strip() for tag in tags.split(",") if tag.strip()],
        meal_types=[MEALS[code].value for code in _codes(meals)],
        cookeo_compatible=Equipment.COOKEO.value in required,
        cookeo_program=program,
        required_equipment=required,
    )


def starter_recipes() -> list[RecipeDTO]:
    return [parse_block(f"## {block}") for block in RECIPES.split("## ")[1:]]


def load_starter_recipes() -> tuple[int, int]:
    """Charge les recettes absentes ; retourne (créées, déjà présentes)."""
    index = load_index()
    created = 0
    recipes = starter_recipes()
    for dto in recipes:
        recipe, is_new = save_recipe(dto, index)
        created += int(is_new)
        if not is_new and recipe.source == RecipeSource.STARTER:
            _refresh(recipe, dto)
    return created, len(recipes) - created


def _refresh(recipe, dto: RecipeDTO) -> None:
    """Répercute les relectures du fichier de données sur une recette de départ déjà en base."""
    Recipe.objects.filter(pk=recipe.pk).update(
        steps=dto.steps,
        tags=dto.tags,
        cookeo_program=dto.cookeo_program,
        prep_minutes=dto.prep_minutes,
        cook_minutes=dto.cook_minutes,
        servings=dto.servings,
    )
