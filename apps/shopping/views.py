from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from apps.core.reference import Aisle
from apps.households.models import HouseholdSettings
from apps.households.permissions import household_required
from apps.planner.models import MenuPlan

from . import services
from .forms import AisleOrderForm, ItemForm, PantryForm
from .models import PantryItem, ShoppingItem


def household_aisle_order(household) -> list[str]:
    """Ordre mémorisé du foyer, complété par les rayons absents (nouveaux rayons, ordre vide)."""
    settings = HouseholdSettings.objects.filter(household=household).first()
    saved = [a for a in (settings.aisle_order if settings else []) if a in Aisle.values]
    return saved + [a for a in Aisle.values if a not in saved]


def _plan(request: HttpRequest, plan_pk) -> MenuPlan:
    return get_object_or_404(MenuPlan.objects.for_household(request.household), pk=plan_pk)


def _item(request: HttpRequest, plan_pk, item_pk) -> ShoppingItem:
    plan = _plan(request, plan_pk)
    return get_object_or_404(ShoppingItem.objects.filter(shopping_list__plan=plan), pk=item_pk)


@require_safe
@household_required
def shopping_detail(request: HttpRequest, plan_pk) -> HttpResponse:
    plan = _plan(request, plan_pk)
    shopping_list = services.list_for(plan)
    items = list(shopping_list.items.filter(hidden=False))
    sections = []
    for aisle in household_aisle_order(request.household):
        in_aisle = sorted(
            (i for i in items if i.aisle == aisle), key=lambda i: (i.checked, i.label.lower())
        )
        if in_aisle:
            sections.append((Aisle(aisle).label, in_aisle))
    context = {
        "plan": plan,
        "sections": sections,
        "form": ItemForm(),
        "remaining": sum(1 for i in items if not i.checked),
        "total": len(items),
    }
    return render(request, "shopping/detail.html", context)


@require_POST
@household_required
def shopping_regenerate(request: HttpRequest, plan_pk) -> HttpResponse:
    services.sync_list(_plan(request, plan_pk))
    messages.success(request, "Liste recalculée : cases cochées et ajouts conservés.")
    return redirect("shopping:detail", plan_pk=plan_pk)


@require_POST
@household_required
def item_toggle(request: HttpRequest, plan_pk, item_pk) -> HttpResponse:
    services.toggle_checked(_item(request, plan_pk, item_pk))
    return redirect("shopping:detail", plan_pk=plan_pk)


@require_POST
@household_required
def item_remove(request: HttpRequest, plan_pk, item_pk) -> HttpResponse:
    services.remove_item(_item(request, plan_pk, item_pk))
    return redirect("shopping:detail", plan_pk=plan_pk)


@require_POST
@household_required
def item_add(request: HttpRequest, plan_pk) -> HttpResponse:
    plan = _plan(request, plan_pk)
    form = ItemForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        services.add_manual_item(
            services.list_for(plan), data["label"], data["quantity"], data["aisle"]
        )
    else:
        messages.error(request, "Article invalide.")
    return redirect("shopping:detail", plan_pk=plan_pk)


@require_http_methods(["GET", "POST"])
@household_required
def pantry(request: HttpRequest) -> HttpResponse:
    form = PantryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        PantryItem.objects.update_or_create(
            household=request.household,
            ingredient=data["ingredient"],
            defaults={
                "always_in_stock": data["always_in_stock"],
                "quantity": data["quantity"],
                "unit": _base_unit(data["ingredient"]),
            },
        )
        return redirect("shopping:pantry")
    items = PantryItem.objects.for_household(request.household).select_related("ingredient")
    return render(request, "shopping/pantry.html", {"form": form, "items": items})


def _base_unit(ingredient) -> str:
    return ingredient.package_unit or ("g" if ingredient.density_g_per_ml is None else "ml")


@require_POST
@household_required
def pantry_remove(request: HttpRequest, pk) -> HttpResponse:
    get_object_or_404(PantryItem.objects.for_household(request.household), pk=pk).delete()
    return redirect("shopping:pantry")


@require_http_methods(["GET", "POST"])
@household_required
def aisle_order(request: HttpRequest) -> HttpResponse:
    current = household_aisle_order(request.household)
    form = AisleOrderForm(request.POST or None, current=current)
    if request.method == "POST" and form.is_valid():
        settings, _ = HouseholdSettings.objects.get_or_create(household=request.household)
        settings.aisle_order = form.ordered()
        settings.save(update_fields=["aisle_order"])
        return redirect("shopping:aisles")
    return render(request, "shopping/aisles.html", {"form": form})
