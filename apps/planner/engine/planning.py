"""Préparation des créneaux : mode de source par créneau et jours « restes » (fonctions pures)."""

import random
from collections.abc import Sequence
from dataclasses import replace
from datetime import timedelta

from .types import MODE_CLASSIC, MODE_COOKEO, MODE_MIXED, SlotSpec

LUNCH = "lunch"
DINNER = "dinner"
PERCENT = 100


def assign_modes(
    slots: Sequence[SlotSpec], mode: str, cookeo_share: int, seed: int
) -> list[SlotSpec]:
    """Répartit les créneaux entre Classique et Cookeo ; le mode mixte respecte la part demandée."""
    if mode != MODE_MIXED:
        return [replace(slot, mode=mode) for slot in slots]
    count = round(len(slots) * cookeo_share / PERCENT)
    chosen = set(random.Random(seed).sample([s.key for s in slots], count))
    return [replace(s, mode=MODE_COOKEO if s.key in chosen else MODE_CLASSIC) for s in slots]


def apply_leftovers(slots: Sequence[SlotSpec], leftover_weekdays: Sequence[int]) -> list[SlotSpec]:
    """Le déjeuner d'un jour « restes » reprend le dîner de la veille, cuisiné en double portion."""
    by_day_meal = {(s.day, s.meal_type): s for s in slots}
    updated = {s.key: s for s in slots}
    for slot in slots:
        if slot.meal_type != LUNCH or slot.day.weekday() not in leftover_weekdays:
            continue
        dinner = by_day_meal.get((slot.day - timedelta(days=1), DINNER))
        if dinner is None or dinner.locked_recipe_id or slot.locked_recipe_id:
            continue
        updated[slot.key] = replace(slot, leftover_from=dinner.key)
        base = updated[dinner.key]
        updated[dinner.key] = replace(
            base, extra_cook_servings=base.extra_cook_servings + slot.servings
        )
    return [updated[s.key] for s in slots]
