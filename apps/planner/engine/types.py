"""Types du moteur de menus : données immuables, sans dépendance à Django."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

COOKEO_CAPACITY = 6  # cuve de 6 L : 6 portions au maximum
MEAL_RANK = {"breakfast": 0, "lunch": 1, "snack": 2, "dinner": 3, "dessert": 4}
MODE_CLASSIC = "classic"
MODE_COOKEO = "cookeo"
MODE_MIXED = "mixed"


@dataclass(frozen=True)
class RecipeView:
    id: str
    title: str
    meal_types: frozenset[str]
    servings: int
    total_minutes: int | None
    cookeo: bool
    required_equipment: frozenset[str]
    allergens: frozenset[str]
    allergens_certain: bool  # faux : ingrédient inconnu ou allergènes non confirmés
    diet_flags: frozenset[str]  # meat, fish, pork, animal, alcohol
    diet_certain: bool
    ingredient_ids: frozenset[int]
    perishable_ids: frozenset[int]
    produce_ids: frozenset[int]
    words: frozenset[str]  # mots repliés des ingrédients, pour les restrictions libres
    tags: frozenset[str] = frozenset()
    protein: str = ""
    cuisine: str = ""
    cost_level: int | None = None

    @property
    def vegetarian(self) -> bool:
        return not ({"meat", "fish"} & self.diet_flags)


@dataclass(frozen=True)
class DinerView:
    id: str
    name: str
    strict_allergens: frozenset[str] = frozenset()
    strict_word_sets: frozenset[frozenset[str]] = frozenset()  # « autre ingrédient » strict
    diets: frozenset[str] = frozenset()
    taste: Mapping[int, int] = field(default_factory=dict)  # ingrédient -> -2..2


@dataclass(frozen=True)
class SlotSpec:
    key: str
    day: date
    meal_type: str
    diner_ids: tuple[str, ...]
    servings: int
    mode: str = MODE_CLASSIC
    max_minutes: int | None = None
    forbidden_equipment: frozenset[str] = frozenset()
    locked_recipe_id: str | None = None
    leftover_from: str | None = None  # clé du créneau dont celui-ci reprend le plat
    extra_cook_servings: int = 0  # portions supplémentaires cuisinées pour des restes

    @property
    def order(self) -> tuple[date, int, str]:
        """Rang chronologique : le jour, puis le moment du repas (déjeuner avant dîner)."""
        rank = MEAL_RANK.get(self.meal_type, len(MEAL_RANK))
        return (self.day, rank, self.key)

    @property
    def cook_servings(self) -> int:
        return self.servings + self.extra_cook_servings

    @property
    def weekend(self) -> bool:
        return self.day.weekday() >= 5  # noqa: PLR2004 - samedi et dimanche


@dataclass(frozen=True)
class EngineSettings:
    equipment: frozenset[str]
    max_minutes_weekday: int = 45
    max_minutes_weekend: int = 90
    min_repeat_days: int = 14
    budget_level: int = 2
    vegetarian_per_week: int = 2
    temperature: float = 0.15
    improvement_swaps: int = 200
    weights: Mapping[str, int] = field(default_factory=dict)
    wanted_tags: frozenset[str] = frozenset()
    allow_cookeo_split: bool = False  # cuire en plusieurs fois au-delà de la cuve de 6 L


@dataclass(frozen=True)
class History:
    last_served: Mapping[str, date] = field(default_factory=dict)
    excluded: frozenset[str] = frozenset()
    favorites: frozenset[str] = frozenset()
    ratings: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Context:
    diners: Mapping[str, DinerView]
    settings: EngineSettings
    history: History
    today: date
    in_season_ids: frozenset[int] = frozenset()
    ingredient_names: Mapping[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Assignment:
    slot_key: str
    recipe_id: str
    explanation: str = ""
    leftover: bool = False


@dataclass(frozen=True)
class GeneratedPlan:
    assignments: tuple[Assignment, ...]
    score: float
