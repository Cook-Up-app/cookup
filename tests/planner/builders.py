"""Fabriques de données pour tester le moteur sans base de données."""

import itertools
from datetime import date, timedelta

from apps.planner.engine import Context, DinerView, EngineSettings, History, RecipeView, SlotSpec

MONDAY = date(2026, 11, 2)
_ids = itertools.count(1)


def recipe(title: str = "", **overrides) -> RecipeView:
    number = next(_ids)
    values = {
        "id": f"r{number}",
        "title": title or f"Recette {number}",
        "meal_types": frozenset({"lunch", "dinner"}),
        "servings": 4,
        "total_minutes": 30,
        "cookeo": False,
        "required_equipment": frozenset(),
        "allergens": frozenset(),
        "allergens_certain": True,
        "diet_flags": frozenset(),
        "diet_certain": True,
        "ingredient_ids": frozenset({number}),
        "perishable_ids": frozenset(),
        "produce_ids": frozenset(),
        "words": frozenset({f"ingredient{number}"}),
    }
    values.update(overrides)
    return RecipeView(**values)


def diner(name: str = "Léa", **overrides) -> DinerView:
    return DinerView(id=overrides.pop("id", name.lower()), name=name, **overrides)


def settings(**overrides) -> EngineSettings:
    overrides.setdefault("equipment", frozenset({"hob", "oven"}))
    return EngineSettings(**overrides)


def context(diners=None, history=None, **settings_overrides) -> Context:
    diners = diners or [diner()]
    return Context(
        diners={d.id: d for d in diners},
        settings=settings(**settings_overrides),
        history=history or History(),
        today=MONDAY,
        ingredient_names={i: f"ingrédient {i}" for i in range(1, 5000)},
    )


def slots(days: int = 7, meals=("lunch", "dinner"), diner_ids=("léa",), start=MONDAY, **overrides):
    result = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        for meal in meals:
            result.append(
                SlotSpec(
                    key=f"{day.isoformat()}:{meal}",
                    day=day,
                    meal_type=meal,
                    diner_ids=tuple(diner_ids),
                    servings=len(diner_ids) or 1,
                    **overrides,
                )
            )
    return result


def catalogue(count: int = 40, **overrides) -> list[RecipeView]:
    return [recipe(**overrides) for _ in range(count)]
