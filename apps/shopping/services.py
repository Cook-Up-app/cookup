"""Liste de courses : construction depuis le menu, régénération sans perte, lignes manuelles."""

import hashlib
import uuid
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction

from apps.catalog.models import Ingredient, RecipeIngredient
from apps.core.reference import Aisle
from apps.planner.models import MenuPlan, MenuSlot

from .aggregation import IngredientInfo, MealNeed, Pantry, RecipeLine, ShoppingLine, aggregate
from .models import PantryItem, ShoppingItem, ShoppingList

DINNER = "dinner"


def signature(plan: MenuPlan) -> str:
    """Empreinte du menu (recettes et portions) : change dès qu'un repas change."""
    rows = plan.slots.values_list("day", "meal_type", "recipe_id", "servings", "leftover")
    text = "|".join(sorted(f"{d}:{m}:{r}:{s}:{int(left)}" for d, m, r, s, left in rows))
    return hashlib.sha256(text.encode()).hexdigest()


def cooked_servings(slots: list[MenuSlot]) -> dict[uuid.UUID, int]:
    """Portions cuisinées par créneau : celles du repas plus celles des restes qui le reprennent."""
    cooked = {slot.pk: slot.servings for slot in slots if not slot.leftover}
    dinners = {(s.day, s.recipe_id): s for s in slots if s.meal_type == DINNER and not s.leftover}
    for slot in slots:
        if slot.leftover:
            source = dinners.get((slot.day - timedelta(days=1), slot.recipe_id))
            if source is not None:
                cooked[source.pk] += slot.servings
    return cooked


def load_needs(plan: MenuPlan) -> list[MealNeed]:
    slots = list(
        plan.slots.filter(recipe__isnull=False, out_of_home=False).select_related("recipe")
    )
    cooked = cooked_servings(slots)
    lines: dict[uuid.UUID, list[RecipeLine]] = defaultdict(list)
    recipe_ids = {s.recipe_id for s in slots}
    for row in RecipeIngredient.objects.filter(recipe_id__in=recipe_ids).order_by("position"):
        base = Decimal(row.base_quantity) if row.base_quantity is not None else None
        lines[row.recipe_id].append(
            RecipeLine(
                row.ingredient_id, _label(row.raw_text), base, row.base_unit, row.is_optional
            )
        )
    return [
        MealNeed(
            str(s.recipe_id), s.recipe.title, s.recipe.servings, cooked[s.pk], lines[s.recipe_id]
        )
        for s in slots
        if s.pk in cooked
    ]


def _label(raw_text: str) -> str:
    from apps.catalog.normalization import parse_line

    return parse_line(raw_text).name or raw_text


def load_infos(ingredient_ids: set[int]) -> dict[int, IngredientInfo]:
    rows = Ingredient.objects.filter(pk__in=ingredient_ids)
    return {
        i.id: IngredientInfo(
            i.id,
            i.name,
            i.aisle,
            i.density_g_per_ml,
            i.is_staple,
            i.package_size,
            i.package_unit,
            i.package_label,
        )  # fmt: skip
        for i in rows
    }


def load_pantry(household) -> Pantry:
    always, wanted, quantities = set(), set(), {}
    for item in PantryItem.objects.for_household(household):
        if item.always_in_stock:
            always.add(item.ingredient_id)
        else:
            wanted.add(item.ingredient_id)
        if item.quantity is not None:
            quantities[item.ingredient_id] = (item.quantity, item.unit)
    return Pantry(frozenset(always), frozenset(wanted), quantities)


def compute_lines(plan: MenuPlan) -> list[ShoppingLine]:
    from apps.households.models import HouseholdSettings

    needs = load_needs(plan)
    ids = {line.ingredient_id for n in needs for line in n.lines if line.ingredient_id}
    settings = HouseholdSettings.objects.filter(household=plan.household).first()
    order = list(settings.aisle_order) if settings else []
    return aggregate(needs, load_infos(ids), load_pantry(plan.household), order)


@transaction.atomic
def sync_list(plan: MenuPlan) -> ShoppingList:
    """Recalcule les lignes automatiques ; garde les cases cochées, les retraits et le manuel."""
    shopping_list, _ = ShoppingList.objects.get_or_create(plan=plan)
    fresh = {line.key: line for line in compute_lines(plan)}
    existing = {i.key: i for i in shopping_list.items.filter(manual=False)}
    stale = [i.pk for key, i in existing.items() if key not in fresh]
    ShoppingItem.objects.filter(pk__in=stale).delete()
    updated, created = [], []
    for key, line in fresh.items():
        if key in existing:
            _apply(existing[key], line)
            updated.append(existing[key])
        else:
            item = ShoppingItem(shopping_list=shopping_list, key=key, manual=False)
            _apply(item, line)
            created.append(item)
    fields = ["label", "ingredient", "quantity", "unit", "aisle", "optional", "recipes", "packs"]
    ShoppingItem.objects.bulk_update(updated, [*fields, "pack_size", "pack_label"])
    ShoppingItem.objects.bulk_create(created)
    shopping_list.signature = signature(plan)
    shopping_list.save(update_fields=["signature", "updated_at"])
    return shopping_list


def _apply(item: ShoppingItem, line: ShoppingLine) -> None:
    item.label, item.ingredient_id = line.label[:200], line.ingredient_id
    item.quantity, item.unit, item.aisle = line.quantity, line.unit, line.aisle
    item.optional, item.recipes = line.optional, [list(r) for r in line.recipes]
    item.packs, item.pack_size, item.pack_label = line.packs, line.pack_size, line.pack_label


def list_for(plan: MenuPlan) -> ShoppingList:
    """Liste du menu, créée ou remise à jour si le menu a changé depuis."""
    existing = ShoppingList.objects.filter(plan=plan).first()
    if existing is None or existing.signature != signature(plan):
        return sync_list(plan)
    return existing


def toggle_checked(item: ShoppingItem) -> ShoppingItem:
    item.checked = not item.checked
    item.save(update_fields=["checked"])
    return item


def remove_item(item: ShoppingItem) -> None:
    """Une ligne manuelle disparaît ; une ligne calculée est masquée pour ne pas revenir."""
    if item.manual:
        item.delete()
        return
    item.hidden = True
    item.save(update_fields=["hidden"])


def add_manual_item(
    shopping_list: ShoppingList,
    label: str,
    quantity: Decimal | None = None,
    aisle: str = Aisle.MISC,
) -> ShoppingItem:
    return ShoppingItem.objects.create(
        shopping_list=shopping_list,
        key=f"manual:{uuid.uuid4()}",
        label=label.strip()[:200],
        quantity=quantity,
        aisle=aisle,
        manual=True,
    )
