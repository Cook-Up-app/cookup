"""Cycle de vie des menus : génération, verrouillage, remplacement, régénération."""

import secrets
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db import transaction

from apps.catalog.models import Recipe
from apps.core.reference import Equipment
from apps.households.models import Household, HouseholdEquipment, HouseholdSettings

from . import loading
from .engine import (
    Context,
    GeneratedPlan,
    RecipeView,
    SlotSpec,
    apply_leftovers,
    assign_modes,
    generate,
    is_allowed,
    suggest_alternatives,
)
from .models import MenuPlan, MenuSlot

MAX_DAYS = 14
SEED_BITS = 62
QUICK_MINUTES = 30


@dataclass(frozen=True)
class PlanRequest:
    start_date: date
    end_date: date
    meals: tuple[str, ...]
    diner_ids: tuple[str, ...]
    guests: int = 0
    mode: str = "classic"
    cookeo_share: int = 50
    quick: bool = False
    split_cookeo: bool = False
    without_equipment: tuple[str, ...] = ()
    wanted_tags: tuple[str, ...] = ()
    out_of_home: tuple[str, ...] = field(default=())  # clés « jour:repas » sans repas à la maison

    def to_params(self) -> dict:
        data = {k: list(v) if isinstance(v, tuple) else v for k, v in self.__dict__.items()}
        data["start_date"], data["end_date"] = (
            self.start_date.isoformat(),
            self.end_date.isoformat(),
        )
        return data

    @classmethod
    def from_params(cls, params: dict) -> "PlanRequest":
        values = dict(params)
        values["start_date"] = date.fromisoformat(values["start_date"])
        values["end_date"] = date.fromisoformat(values["end_date"])
        for name in ("meals", "diner_ids", "without_equipment", "wanted_tags", "out_of_home"):
            values[name] = tuple(values.get(name, ()))
        return cls(**values)


def settings_for(household: Household) -> HouseholdSettings:
    return HouseholdSettings.objects.get_or_create(household=household)[0]


def new_seed() -> int:
    return secrets.randbits(SEED_BITS)


def build_slots(
    request: PlanRequest, household: Household, settings: HouseholdSettings, seed: int
) -> list[SlotSpec]:
    days = (request.end_date - request.start_date).days + 1
    people = len(request.diner_ids) + request.guests
    servings = people or household.default_servings
    specs = []
    for offset in range(days):
        day = request.start_date + timedelta(days=offset)
        for meal in request.meals:
            key = f"{day.isoformat()}:{meal}"
            if key in request.out_of_home:
                continue
            specs.append(
                SlotSpec(
                    key=key,
                    day=day,
                    meal_type=meal,
                    diner_ids=request.diner_ids,
                    servings=servings,
                    max_minutes=QUICK_MINUTES if request.quick else None,
                    forbidden_equipment=frozenset(request.without_equipment),
                )
            )
    mode = request.mode or settings.source_mode
    specs = assign_modes(specs, mode, request.cookeo_share, seed)
    return apply_leftovers(specs, settings.leftover_weekdays)


@dataclass
class Workspace:
    """Tout ce que le moteur lit, chargé une fois par opération."""

    recipes: list[RecipeView]
    ctx: Context

    @property
    def by_id(self) -> dict[str, RecipeView]:
        return {r.id: r for r in self.recipes}


def workspace_for(
    household, settings, request: PlanRequest, today: date, exclude_plan=None
) -> Workspace:
    diners = loading.load_diners(household, request.diner_ids)
    history = loading.load_history(household, exclude_plan=exclude_plan, today=today)
    ctx = loading.build_context(
        household,
        settings,
        diners,
        history,
        today,
        wanted_tags=request.wanted_tags,
        allow_cookeo_split=request.split_cookeo,
    )
    return Workspace(loading.load_recipes(), ctx)


@transaction.atomic
def create_plan(
    household: Household, request: PlanRequest, today: date, seed: int | None = None
) -> MenuPlan:
    """Génère et enregistre un menu ; lève `NotEnoughCandidates` avec le détail du blocage."""
    require_cookeo_if_needed(household, request.mode)
    settings = settings_for(household)
    seed = new_seed() if seed is None else seed
    work = workspace_for(household, settings, request, today)
    slots = build_slots(request, household, settings, seed)
    generated = generate(slots, work.recipes, work.ctx, seed)
    plan = MenuPlan.objects.create(
        household=household,
        start_date=request.start_date,
        end_date=request.end_date,
        params=request.to_params(),
        seed=seed,
    )
    _save_slots(plan, slots, generated, request)
    return plan


def _save_slots(plan: MenuPlan, slots: list[SlotSpec], generated: GeneratedPlan, request) -> None:
    by_key = {a.slot_key: a for a in generated.assignments}
    rows = [
        MenuSlot(
            plan=plan,
            day=spec.day,
            meal_type=spec.meal_type,
            recipe_id=by_key[spec.key].recipe_id,
            servings=spec.servings,
            leftover=by_key[spec.key].leftover,
            explanation=by_key[spec.key].explanation[:400],
            locked=bool(spec.locked_recipe_id),
        )
        for spec in slots
    ]
    for key in request.out_of_home:
        day, meal = key.split(":")
        rows.append(
            MenuSlot(plan=plan, day=date.fromisoformat(day), meal_type=meal, out_of_home=True)
        )
    MenuSlot.objects.bulk_create(rows)


def _specs_with_locks(
    plan: MenuPlan, request: PlanRequest, household, settings, seed
) -> list[SlotSpec]:
    from dataclasses import replace

    locked = {s.key: str(s.recipe_id) for s in plan.slots.filter(locked=True, recipe__isnull=False)}
    specs = build_slots(request, household, settings, seed)
    return [replace(s, locked_recipe_id=locked.get(s.key)) for s in specs]


@transaction.atomic
def regenerate_plan(plan: MenuPlan, today: date) -> MenuPlan:
    """Régénère tout ce qui n'est pas verrouillé, avec une nouvelle graine."""
    household, request = plan.household, PlanRequest.from_params(plan.params)
    settings, seed = settings_for(household), new_seed()
    work = workspace_for(household, settings, request, today, exclude_plan=plan)
    specs = _specs_with_locks(plan, request, household, settings, seed)
    generated = generate(specs, work.recipes, work.ctx, seed)
    by_key = {a.slot_key: a for a in generated.assignments}
    for slot in plan.slots.filter(locked=False, out_of_home=False):
        assignment = by_key.get(slot.key)
        if assignment:
            slot.recipe_id, slot.leftover = assignment.recipe_id, assignment.leftover
            slot.explanation = assignment.explanation[:400]
            slot.save(update_fields=["recipe", "leftover", "explanation"])
    plan.seed = seed
    plan.save(update_fields=["seed"])
    return plan


def toggle_lock(slot: MenuSlot) -> MenuSlot:
    slot.locked = not slot.locked and slot.recipe_id is not None
    slot.save(update_fields=["locked"])
    return slot


def toggle_out_of_home(slot: MenuSlot) -> MenuSlot:
    slot.out_of_home = not slot.out_of_home
    if slot.out_of_home:
        slot.recipe, slot.locked, slot.leftover, slot.explanation = None, False, False, ""
    slot.save(update_fields=["out_of_home", "recipe", "locked", "leftover", "explanation"])
    return slot


def _slot_spec(
    slot: MenuSlot, plan: MenuPlan, request: PlanRequest, household, settings
) -> SlotSpec:
    specs = {s.key: s for s in build_slots(request, household, settings, plan.seed)}
    base = specs.get(slot.key)
    if base is not None:
        return base
    return SlotSpec(slot.key, slot.day, slot.meal_type, request.diner_ids, slot.servings)


def _placed(plan: MenuPlan, work: Workspace, request, household, settings) -> dict:
    by_id = work.by_id
    placed = {}
    for slot in plan.slots.filter(recipe__isnull=False, leftover=False):
        if str(slot.recipe_id) in by_id:
            placed[slot.key] = (
                _slot_spec(slot, plan, request, household, settings),
                by_id[str(slot.recipe_id)],
            )
    return placed


def alternatives_for(slot: MenuSlot, today: date) -> list[Recipe]:
    """Trois recettes permises pour remplacer ce repas (mêmes contraintes que la génération)."""
    plan = slot.plan
    household, request = plan.household, PlanRequest.from_params(plan.params)
    settings = settings_for(household)
    work = workspace_for(household, settings, request, today, exclude_plan=plan)
    spec = _slot_spec(slot, plan, request, household, settings)
    placed = _placed(plan, work, request, household, settings)
    options = suggest_alternatives(spec, placed, work.recipes, work.ctx, seed=new_seed())
    by_pk = Recipe.objects.in_bulk([o.id for o in options])
    return [by_pk[key] for key in map(_uuid, (o.id for o in options)) if key in by_pk]


def _uuid(value: str):
    import uuid

    return uuid.UUID(value)


class CookeoUnavailable(Exception):  # noqa: N818 - nom métier
    """Le mode Cookeo ou mixte est demandé alors que le foyer n'a pas l'équipement."""


def has_cookeo(household: Household) -> bool:
    return (
        HouseholdEquipment.objects.for_household(household)
        .filter(equipment_id=Equipment.COOKEO.value)
        .exists()
    )


def require_cookeo_if_needed(household: Household, mode: str) -> None:
    if mode != "classic" and not has_cookeo(household):
        raise CookeoUnavailable


class ReplacementRefused(Exception):  # noqa: N818 - nom métier
    """La recette demandée ne respecte pas les contraintes dures de ce créneau."""


@transaction.atomic
def replace_slot(slot: MenuSlot, recipe_id: str, today: date) -> MenuSlot:
    """Applique le remplacement après revalidation : une recette interdite n'entre jamais."""
    plan = slot.plan
    household, request = plan.household, PlanRequest.from_params(plan.params)
    settings = settings_for(household)
    work = workspace_for(household, settings, request, today, exclude_plan=plan)
    chosen = work.by_id.get(str(recipe_id))
    spec = _slot_spec(slot, plan, request, household, settings)
    if chosen is None or not is_allowed(chosen, spec, work.ctx):
        raise ReplacementRefused
    slot.recipe_id, slot.leftover, slot.out_of_home = chosen.id, False, False
    slot.explanation = "Choisi par vous."
    slot.save(update_fields=["recipe", "leftover", "out_of_home", "explanation"])
    return slot
