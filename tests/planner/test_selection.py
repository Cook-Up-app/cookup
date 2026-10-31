import random
import time
from datetime import timedelta

import pytest

from apps.planner.engine import (
    History,
    NotEnoughCandidates,
    Violation,
    apply_leftovers,
    assign_modes,
    candidates_for,
    generate,
    is_allowed,
    suggest_alternatives,
)
from tests.planner.builders import MONDAY, catalogue, context, diner, recipe, slots

ALLERGENS = [
    "gluten", "crustaceans", "eggs", "fish", "peanuts", "soy", "milk",
    "tree_nuts", "celery", "mustard", "sesame", "sulphites", "lupin", "molluscs",
]  # fmt: skip


def keys(plan):
    return [a.recipe_id for a in plan.assignments]


def test_same_seed_same_menu_and_other_seeds_differ():
    recipes, week, ctx = catalogue(60), slots(), context()

    first, again = generate(week, recipes, ctx, seed=7), generate(week, recipes, ctx, seed=7)
    others = {tuple(keys(generate(week, recipes, ctx, seed=s))) for s in range(8, 14)}

    assert first == again
    assert len(others | {tuple(keys(first))}) > 1


def test_every_slot_is_filled_with_distinct_recipes():
    plan = generate(slots(), catalogue(60), context(), seed=1)

    assert len(plan.assignments) == 14 and len(set(keys(plan))) == 14


def test_locked_slot_is_kept():
    recipes = catalogue(60)
    week = slots()
    week[3] = type(week[3])(**{**week[3].__dict__, "locked_recipe_id": recipes[10].id})

    plan = generate(week, recipes, context(), seed=2)

    assert plan.assignments[3].recipe_id == recipes[10].id
    assert keys(plan).count(recipes[10].id) == 1


def test_most_constrained_slots_are_filled_first():
    quick_only = [recipe(total_minutes=10) for _ in range(2)]
    others = catalogue(30, total_minutes=40)
    week = slots(2, meals=("lunch",))
    week[0] = type(week[0])(**{**week[0].__dict__, "max_minutes": 15})

    plan = generate(week, quick_only + others, context(), seed=3)

    assert plan.assignments[0].recipe_id in {r.id for r in quick_only}


def test_not_enough_recipes_raises_with_a_precise_report():
    ctx = context([diner(strict_allergens=frozenset({"tree_nuts"}))])
    recipes = catalogue(7, allergens=frozenset({"tree_nuts"})) + catalogue(3, total_minutes=90)

    with pytest.raises(NotEnoughCandidates) as caught:
        generate(slots(1, meals=("lunch",)), recipes, ctx, seed=1)

    report = caught.value.report
    assert (report.total, report.remaining, report.eliminated_percent) == (10, 0, 100)
    assert report.top_reasons(2) == [Violation.ALLERGEN, Violation.TIME]


def test_too_few_distinct_recipes_is_a_failure_not_a_repeat():
    with pytest.raises(NotEnoughCandidates):
        generate(slots(2), catalogue(3), context(), seed=1)


def test_recently_served_recipes_are_avoided():
    recipes = catalogue(40)
    recent = {r.id: MONDAY - timedelta(days=3) for r in recipes[:20]}
    ctx = context(history=History(last_served=recent))

    plan = generate(slots(), recipes, ctx, seed=4)

    assert not set(keys(plan)) & set(recent)


def test_leftovers_reuse_the_previous_dinner_and_double_its_portions():
    week = slots(3)
    prepared = apply_leftovers(week, leftover_weekdays=[1])  # mardi midi = restes du lundi soir
    lunch = next(s for s in prepared if s.key == f"{MONDAY + timedelta(days=1)}:lunch")
    dinner = next(s for s in prepared if s.key == f"{MONDAY}:dinner")

    plan = generate(prepared, catalogue(40), context(), seed=5)

    assert lunch.leftover_from == dinner.key and dinner.extra_cook_servings == lunch.servings
    assert plan.assignments[prepared.index(lunch)].leftover is True
    by_key = {a.slot_key: a.recipe_id for a in plan.assignments}
    assert by_key[lunch.key] == by_key[dinner.key]


def test_leftovers_skip_locked_dinners():
    week = slots(2)
    week[1] = type(week[1])(**{**week[1].__dict__, "locked_recipe_id": "x"})

    assert all(s.leftover_from is None for s in apply_leftovers(week, [1]))


def test_cookeo_capacity_limits_doubled_leftover_dinners():
    cookeo_slots = slots(2, diner_ids=("léa", "tom", "zoé", "max"), mode="cookeo")
    prepared = apply_leftovers(cookeo_slots, [1])  # 4 + 4 = 8 portions > 6
    ctx = context(
        [diner("Léa"), diner("Tom"), diner("Zoé"), diner("Max")], equipment=frozenset({"cookeo"})
    )
    cookeo = catalogue(30, cookeo=True, required_equipment=frozenset({"cookeo"}))

    with pytest.raises(NotEnoughCandidates):
        generate(prepared, cookeo, ctx, seed=1)


def test_mixed_mode_respects_the_requested_share():
    base = slots()

    modes = [s.mode for s in assign_modes(base, "mixed", 50, seed=9)]

    assert modes.count("cookeo") == 7 and modes.count("classic") == 7
    assert assign_modes(base, "mixed", 50, 9) == assign_modes(base, "mixed", 50, 9)
    assert {s.mode for s in assign_modes(base, "cookeo", 0, 1)} == {"cookeo"}


def test_cookeo_mode_only_selects_cookeo_recipes():
    ctx = context(equipment=frozenset({"cookeo", "hob"}))
    recipes = catalogue(20, cookeo=True, required_equipment=frozenset({"cookeo"})) + catalogue(20)
    week = assign_modes(slots(3), "cookeo", 100, 1)

    plan = generate(week, recipes, ctx, seed=1)

    assert all(next(r for r in recipes if r.id == a.recipe_id).cookeo for a in plan.assignments)


def test_tastes_steer_the_selection():
    liked, disliked = (
        recipe(ingredient_ids=frozenset({1000})),
        recipe(ingredient_ids=frozenset({2000})),
    )
    fan = diner(taste={1000: 2, 2000: -2})
    ctx = context([fan])
    picks = [
        generate(slots(1, ("lunch",)), [liked, disliked], ctx, seed=s).assignments[0].recipe_id
        for s in range(30)
    ]

    assert picks.count(liked.id) > 25
    text = generate(slots(1, ("lunch",)), [liked], ctx, seed=1).assignments[0].explanation
    assert "aimé par léa" in text.lower()


def test_antiwaste_explanation_names_the_shared_ingredient():
    cream = frozenset({7})
    first, second = recipe(perishable_ids=cream), recipe(perishable_ids=cream)
    week = slots(2, ("dinner",))

    plan = generate(week, [first, second], context(), seed=1)

    assert (
        "partage ingrédient 7 avec le repas de"
        in plan.assignments[1].explanation + plan.assignments[0].explanation
    )


def test_explanation_is_a_short_sentence_with_duration():
    plan = generate(slots(1, ("lunch",)), [recipe(total_minutes=25)], context(), seed=1)

    text = plan.assignments[0].explanation
    assert "25 min" in text and text.endswith(".") and text[0].isupper()


def test_alternatives_are_three_distinct_allowed_recipes():
    recipes, week, ctx = catalogue(40), slots(3), context()
    plan = generate(week, recipes, ctx, seed=1)
    by_id = {r.id: r for r in recipes}
    placed = {s.key: (s, by_id[a.recipe_id]) for s, a in zip(week, plan.assignments, strict=True)}

    options = suggest_alternatives(week[0], placed, recipes, ctx, seed=3)

    assert len(options) == 3 and len({o.id for o in options}) == 3
    assert plan.assignments[0].recipe_id not in {o.id for o in options}
    assert not {o.id for o in options} & {a.recipe_id for a in plan.assignments}
    assert all(is_allowed(o, week[0], ctx) for o in options)


def test_alternatives_never_break_hard_constraints():
    ctx = context([diner(strict_allergens=frozenset({"eggs"}))])
    safe, unsafe = catalogue(10), catalogue(10, allergens=frozenset({"eggs"}))
    slot = slots(1, ("lunch",))[0]

    options = suggest_alternatives(slot, {}, safe + unsafe, ctx, seed=1)

    assert all("eggs" not in o.allergens for o in options)


def test_improvement_never_lowers_the_score():
    recipes = [
        recipe(perishable_ids=frozenset({i % 5}), protein=("a", "b", "c")[i % 3]) for i in range(40)
    ]
    week, ctx = slots(), context(improvement_swaps=0)
    better = context(improvement_swaps=200)

    plain = [generate(week, recipes, ctx, seed=s).score for s in range(10)]
    improved = [generate(week, recipes, better, seed=s).score for s in range(10)]

    assert sum(improved) >= sum(plain)


def test_candidates_cache_does_not_change_results():
    recipes, week, ctx = catalogue(30), slots(), context()

    pools = candidates_for(week, recipes, ctx)

    assert all(len(pool) == 30 for pool in pools.values())


def test_no_strict_allergen_in_1000_random_generations():
    """Test par propriété : quelles que soient les allergies, aucun menu ne les enfreint."""
    rng = random.Random(2026)
    violations_found = 0
    generated = 0
    for iteration in range(1000):
        recipes = [
            recipe(
                allergens=frozenset(rng.sample(ALLERGENS, rng.randint(0, 3))),
                allergens_certain=rng.random() > 0.15,
                total_minutes=rng.choice([None, 15, 30, 60, 100]),
            )
            for _ in range(60)
        ]
        diners = [
            diner(
                f"D{i}",
                id=f"d{i}",
                strict_allergens=frozenset(rng.sample(ALLERGENS, rng.randint(0, 3))),
            )
            for i in range(rng.randint(1, 4))
        ]
        ctx = context(diners)
        week = slots(rng.randint(1, 3), diner_ids=[d.id for d in diners])
        try:
            plan = generate(week, recipes, ctx, seed=iteration)
        except NotEnoughCandidates:
            continue
        generated += 1
        by_id = {r.id: r for r in recipes}
        strict = set().union(*(d.strict_allergens for d in diners))
        for assignment in plan.assignments:
            chosen = by_id[assignment.recipe_id]
            if chosen.allergens & strict or (strict and not chosen.allergens_certain):
                violations_found += 1
    assert generated > 500
    assert violations_found == 0


def test_a_week_on_two_thousand_recipes_takes_under_two_seconds():
    rng = random.Random(1)
    recipes = [
        recipe(
            ingredient_ids=frozenset(rng.sample(range(1, 300), 8)),
            perishable_ids=frozenset(rng.sample(range(1, 300), 3)),
            produce_ids=frozenset(rng.sample(range(1, 300), 3)),
            allergens=frozenset(rng.sample(ALLERGENS, rng.randint(0, 2))),
            protein=rng.choice(["volaille", "poisson", "porc", ""]),
            total_minutes=rng.choice([15, 30, 45, 60]),
        )
        for _ in range(2000)
    ]
    ctx = context([diner(strict_allergens=frozenset({"tree_nuts"}))])
    week = slots()
    generate(week, recipes, ctx, seed=0)  # chauffe

    started = time.perf_counter()
    generate(week, recipes, ctx, seed=1)

    assert time.perf_counter() - started < 2.0


def test_lunch_comes_before_dinner_for_the_previous_meal_rule():
    day = slots(1)
    lunch, dinner = day[0], day[1]

    assert lunch.order < dinner.order
    plan = generate(
        day,
        [recipe(protein="porc"), recipe(protein="porc"), recipe(protein="poisson")],
        context(),
        seed=1,
    )
    explanation = next(a.explanation for a in plan.assignments if a.slot_key == dinner.key)
    assert plan.assignments[0].slot_key == lunch.key and explanation != ""
