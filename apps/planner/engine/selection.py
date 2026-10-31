"""Sélection reproductible : créneaux les plus contraints d'abord, tirage pondéré, échanges."""

import math
import random
from collections.abc import Sequence

from .criteria import PlanState, explanation, total_score
from .failure import NotEnoughCandidates, analyse
from .rules import RULES, is_allowed, recent_rule
from .types import (
    COOKEO_CAPACITY,
    Assignment,
    Context,
    GeneratedPlan,
    RecipeView,
    SlotSpec,
)

SCORE_SCALE = 100
ALTERNATIVES = 3
_STATIC_RULES = tuple(rule for rule in RULES if rule is not recent_rule)


def _signature(slot: SlotSpec) -> tuple:
    return (
        slot.meal_type,
        slot.diner_ids,
        slot.mode,
        slot.max_minutes,
        slot.forbidden_equipment,
        slot.cook_servings > COOKEO_CAPACITY,
        slot.weekend,
    )


def candidates_for(
    slots: Sequence[SlotSpec], recipes: Sequence[RecipeView], ctx: Context
) -> dict[str, list[RecipeView]]:
    """Recettes permises par créneau ; les règles indépendantes de la date sont mises en cache."""
    cache: dict[tuple, list[RecipeView]] = {}
    result: dict[str, list[RecipeView]] = {}
    for slot in slots:
        key = _signature(slot)
        if key not in cache:
            cache[key] = [
                r for r in recipes if all(rule(r, slot, ctx) is None for rule in _STATIC_RULES)
            ]
        result[slot.key] = [r for r in cache[key] if recent_rule(r, slot, ctx) is None]
    return result


def _weighted_pick(
    pool: list[RecipeView], slot: SlotSpec, ctx: Context, state: PlanState, rng: random.Random
) -> RecipeView:
    scores = [total_score(r, slot, ctx, state) for r in pool]
    best = max(scores)
    temperature = max(ctx.settings.temperature, 1e-6) * SCORE_SCALE
    weights = [math.exp((s - best) / temperature) for s in scores]
    return rng.choices(pool, weights=weights, k=1)[0]


def _objective(state: PlanState, ctx: Context) -> float:
    return sum(total_score(r, s, ctx, state) for s, r in state.placed.values())


def _try_swap(state, free, allowed_ids, ctx, rng, pool_by_slot) -> None:
    """Un essai d'amélioration : échange deux créneaux, ou remplace par une recette inutilisée."""
    first = rng.choice(free)
    before = _objective(state, ctx)
    old = state.placed[first.key]
    if rng.random() < 0.5 and len(free) > 1:  # noqa: PLR2004
        second = rng.choice([s for s in free if s.key != first.key])
        other = state.placed[second.key]
        if old[1].id not in allowed_ids[second.key] or other[1].id not in allowed_ids[first.key]:
            return
        state.placed[first.key], state.placed[second.key] = (first, other[1]), (second, old[1])
        if _objective(state, ctx) <= before:
            state.placed[first.key], state.placed[second.key] = old, other
        return
    used = {r.id for _, r in state.placed.values()}
    unused = [r for r in pool_by_slot[first.key] if r.id not in used]
    if not unused:
        return
    state.placed[first.key] = (first, rng.choice(unused))
    if _objective(state, ctx) <= before:
        state.placed[first.key] = old


def _improve(state, free, pool_by_slot, ctx, rng) -> None:
    if len(free) < 1:
        return
    allowed_ids = {key: {r.id for r in pool} for key, pool in pool_by_slot.items()}
    for _ in range(ctx.settings.improvement_swaps):
        _try_swap(state, free, allowed_ids, ctx, rng, pool_by_slot)


def generate(
    slots: Sequence[SlotSpec], recipes: Sequence[RecipeView], ctx: Context, seed: int
) -> GeneratedPlan:
    """Même graine, mêmes données : même menu ; lève `NotEnoughCandidates` si c'est impossible."""
    rng = random.Random(seed)
    by_id = {r.id: r for r in recipes}
    state = PlanState()
    for slot in slots:
        if slot.locked_recipe_id:
            state.placed[slot.key] = (slot, by_id[slot.locked_recipe_id])
    free = [s for s in slots if not s.locked_recipe_id and not s.leftover_from]
    pools = candidates_for(free, recipes, ctx)
    used = {r.id for _, r in state.placed.values()}
    for slot in sorted(free, key=lambda s: (len(pools[s.key]), s.day, s.key)):
        pool = sorted((r for r in pools[slot.key] if r.id not in used), key=lambda r: r.id)
        if not pool:
            raise NotEnoughCandidates(analyse(slot, list(recipes), ctx, len(pools[slot.key])))
        pick = _weighted_pick(pool, slot, ctx, state, rng)
        state.placed[slot.key] = (slot, pick)
        used.add(pick.id)
    _improve(state, free, pools, ctx, rng)
    return _assemble(slots, state, ctx)


def _assemble(slots: Sequence[SlotSpec], state: PlanState, ctx: Context) -> GeneratedPlan:
    assignments = []
    for slot in slots:
        if slot.leftover_from:
            source = state.placed[slot.leftover_from][1]
            assignments.append(Assignment(slot.key, source.id, "Restes du repas précédent.", True))
            continue
        recipe = state.placed[slot.key][1]
        assignments.append(Assignment(slot.key, recipe.id, explanation(recipe, slot, ctx, state)))
    scores = [total_score(r, s, ctx, state) for s, r in state.placed.values()]
    return GeneratedPlan(tuple(assignments), sum(scores) / len(scores) if scores else 0.0)


def suggest_alternatives(
    slot: SlotSpec,
    placed: dict[str, tuple[SlotSpec, RecipeView]],
    recipes: Sequence[RecipeView],
    ctx: Context,
    seed: int,
    count: int = ALTERNATIVES,
) -> list[RecipeView]:
    """Trois propositions pour remplacer un repas, tirées sans remise parmi les permises."""
    rng = random.Random(seed)
    state = PlanState(dict(placed))
    used = {r.id for key, (_, r) in placed.items() if key != slot.key}
    pool = sorted(
        (r for r in recipes if r.id not in used and is_allowed(r, slot, ctx)), key=lambda r: r.id
    )
    current = placed.get(slot.key)
    if current:
        pool = [r for r in pool if r.id != current[1].id]
    picks: list[RecipeView] = []
    while pool and len(picks) < count:
        choice = _weighted_pick(pool, slot, ctx, state, rng)
        picks.append(choice)
        pool.remove(choice)
    return picks
