"""Cas chiffrés de la section 8 de la spécification, sans base de données."""

import pytest

from apps.core.reference import Aisle
from apps.shopping.aggregation import IngredientInfo, MealNeed, Pantry, aggregate, round_purchasable
from tests.shopping.builders import D, infos, line, need

OIL = {"id": 1, "name": "huile d'olive"}
ONION = {"id": 2, "name": "oignon", "aisle": Aisle.FRUITS_VEGETABLES}
MILK = {"id": 3, "name": "lait", "aisle": Aisle.DAIRY, "density_g_per_ml": D("1.03")}
FLOUR = {"id": 4, "name": "farine"}
CHICKEN = {"id": 5, "name": "poulet", "aisle": Aisle.BUTCHER_FISH}
TOMATOES = {
    "id": 6, "name": "tomates concassées", "aisle": Aisle.SAVORY_GROCERY,
    "package_size": D(400), "package_unit": "g", "package_label": "boîte",
}  # fmt: skip
EGG = {"id": 7, "name": "œuf", "aisle": Aisle.DAIRY}
INFOS = infos(
    oil=OIL, onion=ONION, milk=MILK, flour=FLOUR, chicken=CHICKEN, tomatoes=TOMATOES, egg=EGG
)


def only(lines):
    assert len(lines) == 1, lines
    return lines[0]


def test_spoons_and_millilitres_add_up_to_60_ml():
    meals = [
        need("2 c. à soupe d'huile", ids={"2 c. à soupe d'huile": 1}, recipe_id="a"),
        need("30 ml d'huile", ids={"30 ml d'huile": 1}, recipe_id="b"),
    ]

    result = only(aggregate(meals, INFOS))

    assert (result.quantity, result.unit, result.label) == (60, "ml", "huile d'olive")


def test_half_onion_plus_one_onion_is_rounded_up_to_two():
    meals = [
        need("1/2 oignon", ids={"1/2 oignon": 2}, recipe_id="a"),
        need("1 oignon", ids={"1 oignon": 2}, recipe_id="b"),
    ]

    result = only(aggregate(meals, INFOS))

    assert (result.quantity, result.unit) == (2, "pièce")


def test_quantities_are_scaled_to_the_servings_of_the_slot():
    meals = [need("200 g de farine", ids={"200 g de farine": 4}, servings=4, cook=6)]

    assert only(aggregate(meals, INFOS, Pantry(not_in_stock=frozenset({4})))).quantity == 300


def test_mass_and_volume_merge_with_a_known_density():
    meals = [
        need("100 g de lait", ids={"100 g de lait": 3}, recipe_id="a"),
        need("20 cl de lait", ids={"20 cl de lait": 3}, recipe_id="b"),
    ]

    result = only(aggregate(meals, INFOS))

    assert result.unit == "g" and result.quantity == 310  # 100 + 200 × 1,03 = 306, arrondi


def test_mass_and_volume_stay_separate_without_density():
    no_density = dict(INFOS)
    no_density[3] = IngredientInfo(3, "lait", Aisle.DAIRY)
    meals = [
        need("100 g de lait", ids={"100 g de lait": 3}),
        need("20 cl de lait", ids={"20 cl de lait": 3}, recipe_id="b"),
    ]

    result = aggregate(meals, no_density)

    assert sorted((r.unit, r.quantity) for r in result) == [("g", 100), ("ml", 200)]


def test_staples_are_left_out_unless_the_household_wants_them():
    meals = [need("200 g de farine", ids={"200 g de farine": 4})]
    flour_as_staple = {**INFOS, 4: IngredientInfo(4, "farine", staple=True)}

    assert aggregate(meals, flour_as_staple) == []
    assert len(aggregate(meals, flour_as_staple, Pantry(not_in_stock=frozenset({4})))) == 1


def test_always_in_stock_items_are_removed():
    meals = [need("2 c. à soupe d'huile", ids={"2 c. à soupe d'huile": 1})]

    assert aggregate(meals, INFOS, Pantry(always_in_stock=frozenset({1}))) == []


def test_pantry_quantity_is_deducted():
    meals = [need("500 g de poulet", ids={"500 g de poulet": 5})]

    result = only(aggregate(meals, INFOS, Pantry(quantities={5: (D(200), "g")})))

    assert result.quantity == 300
    assert aggregate(meals, INFOS, Pantry(quantities={5: (D(800), "g")})) == []


def test_pantry_stock_in_another_unit_is_ignored():
    meals = [need("500 g de poulet", ids={"500 g de poulet": 5})]

    assert only(aggregate(meals, INFOS, Pantry(quantities={5: (D(2), "pièce")}))).quantity == 500


def test_meat_is_rounded_by_fifty_grams_and_other_goods_by_ten():
    meat = only(aggregate([need("620 g de poulet", ids={"620 g de poulet": 5})], INFOS))
    flour = only(aggregate([need("333 g de farine", ids={"333 g de farine": 4})], INFOS))

    assert meat.quantity == 650 and flour.quantity == 340


def test_package_size_gives_a_number_of_packs():
    result = only(
        aggregate(
            [need("650 g de tomates concassées", ids={"650 g de tomates concassées": 6})], INFOS
        )
    )

    assert (result.quantity, result.packs, result.pack_size, result.pack_label) == (
        650,
        2,
        400,
        "boîte",
    )


def test_eggs_are_counted_in_whole_units():
    result = only(aggregate([need("2,5 œufs", ids={"2,5 œufs": 7})], INFOS))

    assert (result.quantity, result.unit) == (3, "pièce")


def test_optional_only_when_every_use_is_optional():
    both = [
        MealNeed("a", "A", 4, 4, [line("1 c. à café de piment (facultatif)", 1)]),
        MealNeed("b", "B", 4, 4, [line("1 c. à café de piment", 1)]),
    ]
    only_optional = both[:1]

    assert only(aggregate(both, INFOS)).optional is False
    assert only(aggregate(only_optional, INFOS)).optional is True


def test_origin_recipes_are_kept_for_every_line():
    meals = [
        need("1 oignon", ids={"1 oignon": 2}, recipe_id="a", title="Soupe"),
        need("1 oignon", ids={"1 oignon": 2}, recipe_id="b", title="Quiche"),
    ]

    assert only(aggregate(meals, INFOS)).recipes == (("b", "Quiche"), ("a", "Soupe"))


def test_unmatched_ingredients_keep_their_text_and_merge_by_text():
    meals = [need("2 pierres de lune", recipe_id="a"), need("3 pierres de lune", recipe_id="b")]

    result = only(aggregate(meals, INFOS))

    assert (
        result.ingredient_id is None and result.quantity == 5 and "pierres de lune" in result.label
    )


def test_uncounted_units_do_not_create_a_quantity():
    result = only(
        aggregate(
            [need("1 pincée de safran", ids={"1 pincée de safran": 99})],
            {99: IngredientInfo(99, "safran")},
        )
    )

    assert result.quantity is None and result.unit == ""


def test_uncounted_use_joins_the_quantified_line():
    meals = [
        need("2 c. à soupe de miel", ids={"2 c. à soupe de miel": 8}, recipe_id="a"),
        need("1 filet de miel", ids={"1 filet de miel": 8}, recipe_id="b"),
    ]

    result = only(aggregate(meals, {8: IngredientInfo(8, "miel", Aisle.SWEET_GROCERY)}))

    assert result.quantity == 30 and len(result.recipes) == 2


def test_lines_follow_the_aisle_order_and_it_can_be_reordered():
    meals = [
        need("1 oignon", ids={"1 oignon": 2}),
        need("500 g de poulet", ids={"500 g de poulet": 5}, recipe_id="b"),
    ]

    default = [r.aisle for r in aggregate(meals, INFOS)]
    custom = [
        r.aisle
        for r in aggregate(meals, INFOS, aisle_order=[Aisle.BUTCHER_FISH, Aisle.FRUITS_VEGETABLES])
    ]

    assert default == [Aisle.FRUITS_VEGETABLES, Aisle.BUTCHER_FISH]
    assert custom == [Aisle.BUTCHER_FISH, Aisle.FRUITS_VEGETABLES]


def test_keys_are_stable_across_runs_and_scale_changes():
    first = only(aggregate([need("1 oignon", ids={"1 oignon": 2}, cook=4)], INFOS))
    second = only(aggregate([need("1 oignon", ids={"1 oignon": 2}, cook=8)], INFOS))

    assert first.key == second.key == "ing:2:pièce" and second.quantity == 2


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [(D("0.2"), "pièce", 1), (D("1.01"), "pièce", 2), (D("5"), "g", 10), (D("101"), "ml", 110)],
)
def test_round_up_never_rounds_down(quantity, unit, expected):
    assert round_purchasable(quantity, unit, None)[0] == expected


BUTTER = {
    "id": 9, "name": "beurre", "aisle": Aisle.DAIRY, "density_g_per_ml": D("0.91"),
    "package_size": D(250), "package_unit": "g", "package_label": "plaquette",
}  # fmt: skip


def test_ingredient_sold_by_weight_listed_in_spoons_is_converted_to_grams():
    meals = [need("1 c. à soupe de beurre", ids={"1 c. à soupe de beurre": 9})]

    result = only(aggregate(meals, infos(butter=BUTTER)))

    assert (result.unit, result.quantity) == ("g", 20)  # 15 ml × 0,91 = 13,65 g, arrondi


def test_liquid_without_weight_packaging_stays_in_millilitres():
    meals = [need("2 c. à soupe de lait", ids={"2 c. à soupe de lait": 3})]

    assert only(aggregate(meals, INFOS)).unit == "ml"
