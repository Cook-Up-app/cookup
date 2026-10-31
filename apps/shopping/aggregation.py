"""Calcul de la liste de courses : fonctions pures, sans Django (SPEC section 8)."""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal

from apps.catalog.text import stem_key
from apps.core.reference import Aisle

GRAM, MILLILITRE, PIECE = "g", "ml", "pièce"
MEAT_STEP = Decimal(50)  # viande et poisson : par pas de 50 g
WEIGHT_STEP = Decimal(10)
VOLUME_STEP = Decimal(10)
ZERO = Decimal(0)


@dataclass(frozen=True)
class RecipeLine:
    ingredient_id: int | None
    label: str
    base_quantity: Decimal | None  # en g, ml ou pièces ; None si non convertible
    base_unit: str
    optional: bool = False


@dataclass(frozen=True)
class MealNeed:
    recipe_id: str
    recipe_title: str
    recipe_servings: int
    cook_servings: int  # portions réellement cuisinées (restes compris)
    lines: Sequence[RecipeLine]


@dataclass(frozen=True)
class IngredientInfo:
    id: int
    name: str
    aisle: str = Aisle.MISC
    density_g_per_ml: Decimal | None = None
    staple: bool = False
    package_size: Decimal | None = None
    package_unit: str = ""
    package_label: str = ""


@dataclass(frozen=True)
class Pantry:
    always_in_stock: frozenset[int] = frozenset()
    not_in_stock: frozenset[int] = frozenset()  # produit de base que le foyer veut racheter
    quantities: Mapping[int, tuple[Decimal, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class ShoppingLine:
    key: str  # stable d'une génération à l'autre : sert à conserver les cases cochées
    label: str
    ingredient_id: int | None
    quantity: Decimal | None
    unit: str
    aisle: str
    optional: bool
    recipes: tuple[tuple[str, str], ...]
    packs: int | None = None
    pack_size: Decimal | None = None
    pack_label: str = ""


@dataclass
class _Tally:
    label: str
    ingredient_id: int | None
    amounts: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    optional: bool = True
    recipes: dict[str, str] = field(default_factory=dict)


def _group_key(line: RecipeLine) -> str:
    return f"ing:{line.ingredient_id}" if line.ingredient_id else f"txt:{stem_key(line.label)}"


def _collect(needs: Iterable[MealNeed], infos: Mapping[int, IngredientInfo]) -> dict[str, _Tally]:
    """Étapes 1 et 2 : mise à l'échelle des portions puis somme par ingrédient et unité de base."""
    tallies: dict[str, _Tally] = {}
    for need in needs:
        factor = Decimal(need.cook_servings) / Decimal(need.recipe_servings or 1)
        for line in need.lines:
            key = _group_key(line)
            info = infos.get(line.ingredient_id) if line.ingredient_id else None
            tally = tallies.setdefault(
                key, _Tally(info.name if info else line.label, line.ingredient_id)
            )
            tally.optional = tally.optional and line.optional
            tally.recipes[need.recipe_id] = need.recipe_title
            if line.base_quantity is not None and line.base_unit:
                tally.amounts[line.base_unit] += line.base_quantity * factor
            else:
                tally.amounts[""] += ZERO  # présent sans quantité (pincée, « sel »…)
    return tallies


def _merge_mass_and_volume(
    amounts: dict[str, Decimal], info: IngredientInfo | None
) -> dict[str, Decimal]:
    """Étape 3 : masse et volume s'additionnent si la densité est connue, sinon deux lignes.

    Un ingrédient qui s'achète au poids (conditionnement en g) et n'apparaît qu'en volume
    (« 1 c. à soupe de beurre ») est aussi converti en grammes, quand sa densité est connue.
    """
    density = info.density_g_per_ml if info else None
    if not density or MILLILITRE not in amounts:
        return amounts
    sold_by_weight = bool(info and info.package_unit == GRAM)
    if GRAM in amounts or sold_by_weight:
        merged = dict(amounts)
        merged[GRAM] = merged.get(GRAM, ZERO) + merged.pop(MILLILITRE) * density
        return merged
    return amounts


def _ceil_to(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _round_up(quantity: Decimal, unit: str, info: IngredientInfo | None) -> Decimal:
    if unit == PIECE:
        return _ceil_to(quantity, Decimal(1))
    if unit == GRAM:
        step = MEAT_STEP if info and info.aisle == Aisle.BUTCHER_FISH else WEIGHT_STEP
        return _ceil_to(quantity, step)
    return _ceil_to(quantity, VOLUME_STEP)


def round_purchasable(
    quantity: Decimal, unit: str, info: IngredientInfo | None
) -> tuple[Decimal, int | None]:
    """Étape 5 : quantité achetable et, si l'ingrédient a un conditionnement, le nombre d'unités."""
    packs = None
    if info and info.package_size and info.package_unit == unit:
        packs = int(_ceil_to(quantity / info.package_size, Decimal(1)))
    return _round_up(quantity, unit, info), packs


def _pantry_filter(
    ingredient_id: int | None,
    unit: str,
    quantity: Decimal | None,
    info: IngredientInfo | None,
    pantry: Pantry,
) -> Decimal | None | bool:
    """Étape 4 : retire le placard. Retourne False pour exclure, sinon la quantité restante."""
    if ingredient_id is None:
        return quantity
    if ingredient_id in pantry.always_in_stock:
        return False
    if info and info.staple and ingredient_id not in pantry.not_in_stock:
        return False
    stock = pantry.quantities.get(ingredient_id)
    if stock and quantity is not None and stock[1] == unit:
        remaining = quantity - stock[0]
        return remaining if remaining > 0 else False
    return quantity


def _line(key, tally, unit, quantity, info, aisle, packs) -> ShoppingLine:
    return ShoppingLine(
        key=f"{key}:{unit or 'none'}",
        label=tally.label,
        ingredient_id=tally.ingredient_id,
        quantity=quantity,
        unit=unit,
        aisle=aisle,
        optional=tally.optional,
        recipes=tuple(sorted(tally.recipes.items(), key=lambda item: item[1])),
        packs=packs,
        pack_size=info.package_size if packs and info else None,
        pack_label=info.package_label if packs and info else "",
    )


def _lines_for(
    key: str, tally: _Tally, info: IngredientInfo | None, pantry: Pantry
) -> list[ShoppingLine]:
    amounts = _merge_mass_and_volume(tally.amounts, info)
    quantified = {unit: qty for unit, qty in amounts.items() if unit}
    aisle = info.aisle if info else Aisle.MISC
    lines = []
    for unit, quantity in sorted(quantified.items()):
        left = _pantry_filter(tally.ingredient_id, unit, quantity, info, pantry)
        if left is False:
            continue
        rounded, packs = round_purchasable(left, unit, info)
        lines.append(_line(key, tally, unit, rounded, info, aisle, packs))
    if not quantified and _pantry_filter(tally.ingredient_id, "", None, info, pantry) is not False:
        lines.append(_line(key, tally, "", None, info, aisle, None))
    return lines


def aggregate(
    needs: Iterable[MealNeed],
    infos: Mapping[int, IngredientInfo],
    pantry: Pantry | None = None,
    aisle_order: Sequence[str] = (),
) -> list[ShoppingLine]:
    """Liste consolidée : portions mises à l'échelle, quantités additionnées, placard retiré."""
    pantry = pantry or Pantry()
    result: list[ShoppingLine] = []
    for key, tally in _collect(needs, infos).items():
        info = infos.get(tally.ingredient_id) if tally.ingredient_id else None
        result.extend(_lines_for(key, tally, info, pantry))
    order = {aisle: rank for rank, aisle in enumerate(aisle_order or [a.value for a in Aisle])}
    return sorted(
        result, key=lambda line: (order.get(line.aisle, len(order)), line.label.lower(), line.key)
    )
