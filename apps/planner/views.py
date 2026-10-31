from datetime import date

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from apps.households.permissions import household_required

from . import services
from .engine import NotEnoughCandidates
from .engine.types import MEAL_RANK
from .forms import PlanForm
from .messages import describe_failure
from .models import MenuPlan, MenuSlot

PLANS_PER_PAGE = 20


def _today() -> date:
    return timezone.localdate()


def _plan(request: HttpRequest, pk) -> MenuPlan:
    return get_object_or_404(MenuPlan.objects.for_household(request.household), pk=pk)


def _slot(request: HttpRequest, pk, slot_pk) -> MenuSlot:
    plan = _plan(request, pk)
    return get_object_or_404(MenuSlot.objects.select_related("plan").filter(plan=plan), pk=slot_pk)


@require_safe
@household_required
def menu_list(request: HttpRequest) -> HttpResponse:
    plans = MenuPlan.objects.for_household(request.household)
    page = Paginator(plans, PLANS_PER_PAGE).get_page(request.GET.get("page"))
    return render(request, "planner/list.html", {"page": page})


def _form(request: HttpRequest, data=None) -> PlanForm:
    household = request.household
    settings = services.settings_for(household)
    has_cookeo = services.has_cookeo(household)
    initial = {
        "start_date": _today(),
        "meals": settings.meals,
        "mode": settings.source_mode if has_cookeo else "classic",
        "cookeo_share": settings.cookeo_share,
        "diners": household.diners.all(),
    }
    return PlanForm(data, initial=initial, household=household, has_cookeo=has_cookeo)


@require_http_methods(["GET", "POST"])
@household_required
def menu_new(request: HttpRequest) -> HttpResponse:
    """Formulaire « Nouveau menu » ; la génération elle-même est dans `menu_generate` (POST)."""
    form = _form(request, request.POST or None)
    if request.method == "POST":
        return _generate(request, form)
    return render(request, "planner/new.html", {"form": form})


def _generate(request: HttpRequest, form: PlanForm) -> HttpResponse:
    if not form.is_valid():
        return render(request, "planner/new.html", {"form": form})
    try:
        plan = services.create_plan(request.household, form.to_request(), _today())
    except NotEnoughCandidates as failure:
        messages.error(request, describe_failure(failure.report))
        return render(request, "planner/new.html", {"form": form})
    except services.CookeoUnavailable:
        form.add_error("mode", "Le mode Cookeo exige l'équipement Cookeo dans le foyer.")
        return render(request, "planner/new.html", {"form": form})
    return redirect("planner:detail", pk=plan.pk)


@require_POST
@household_required
def menu_generate(request: HttpRequest) -> HttpResponse:
    return _generate(request, _form(request, request.POST))


@require_safe
@household_required
def menu_detail(request: HttpRequest, pk) -> HttpResponse:
    plan = _plan(request, pk)
    slots = sorted(
        plan.slots.select_related("recipe"), key=lambda s: (s.day, MEAL_RANK.get(s.meal_type, 9))
    )
    days: dict[date, list[MenuSlot]] = {}
    for slot in slots:
        days.setdefault(slot.day, []).append(slot)
    context = {"plan": plan, "days": days.items(), "today": _today()}
    return render(request, "planner/detail.html", context)


@require_POST
@household_required
def slot_lock(request: HttpRequest, pk, slot_pk) -> HttpResponse:
    services.toggle_lock(_slot(request, pk, slot_pk))
    return redirect("planner:detail", pk=pk)


@require_POST
@household_required
def slot_out_of_home(request: HttpRequest, pk, slot_pk) -> HttpResponse:
    services.toggle_out_of_home(_slot(request, pk, slot_pk))
    return redirect("planner:detail", pk=pk)


@require_POST
@household_required
def slot_replace(request: HttpRequest, pk, slot_pk) -> HttpResponse:
    """Sans `recipe` : propose trois alternatives ; avec `recipe` : applique après revalidation."""
    slot = _slot(request, pk, slot_pk)
    chosen = request.POST.get("recipe")
    if not chosen:
        options = services.alternatives_for(slot, _today())
        return render(request, "planner/replace.html", {"slot": slot, "options": options})
    try:
        services.replace_slot(slot, chosen, _today())
    except (services.ReplacementRefused, ValueError) as error:
        raise Http404 from error
    return redirect("planner:detail", pk=pk)


@require_POST
@household_required
def menu_regenerate(request: HttpRequest, pk) -> HttpResponse:
    plan = _plan(request, pk)
    try:
        services.regenerate_plan(plan, _today())
    except NotEnoughCandidates as failure:
        messages.error(request, describe_failure(failure.report))
    return redirect("planner:detail", pk=pk)
