"""Structure commune d'une recette, produite par toutes les sources (SPEC section 6)."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RecipeDTO:
    source: str
    title: str
    ingredient_lines: list[str]
    steps: list[str]
    source_ref: str = ""
    url: str = ""
    image_url: str = ""
    servings: int = 4
    prep_minutes: int | None = None
    cook_minutes: int | None = None
    difficulty: str = ""
    cost_level: int | None = None
    tags: list[str] = field(default_factory=list)
    meal_types: list[str] = field(default_factory=list)
    cookeo_compatible: bool = False
    cookeo_program: dict = field(default_factory=dict)
    required_equipment: list[str] = field(default_factory=list)
    optional_equipment: list[str] = field(default_factory=list)
    rating: float | None = None  # note publiée par la source, pour filtrer à l'import
