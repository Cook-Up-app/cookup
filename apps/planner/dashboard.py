"""Données de l'accueil : repas du jour et du lendemain, avancement des courses."""

from datetime import date, timedelta

from apps.shopping.models import ShoppingItem

from .engine.types import MEAL_RANK
from .models import MenuPlan, MenuSlot


def _meals(plan: MenuPlan, day: date) -> list[MenuSlot]:
    slots = plan.slots.filter(day=day).select_related("recipe")
    return sorted(slots, key=lambda slot: MEAL_RANK.get(slot.meal_type, len(MEAL_RANK)))


def current_plan(household, today: date) -> MenuPlan | None:
    """Menu qui couvre aujourd'hui, sinon le plus récent à venir, sinon le dernier."""
    plans = MenuPlan.objects.for_household(household)
    return (
        plans.filter(start_date__lte=today, end_date__gte=today).first()
        or plans.filter(start_date__gt=today).order_by("start_date").first()
        or plans.first()
    )


def build(household, today: date) -> dict:
    plan = current_plan(household, today)
    if plan is None:
        return {"plan": None}
    remaining = ShoppingItem.objects.filter(
        shopping_list__plan=plan, hidden=False, checked=False
    ).count()
    return {
        "plan": plan,
        "today": _meals(plan, today),
        "tomorrow": _meals(plan, today + timedelta(days=1)),
        "shopping_remaining": remaining,
    }
