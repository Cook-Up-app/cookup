from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.households.models import Diner
from apps.households.permissions import household_required

from . import services, steps


def owner_only(view):
    """Réservé au propriétaire ; un simple membre est renvoyé à l'accueil, sans erreur."""

    @household_required
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not request.membership.is_owner:
            return redirect("core:home")
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


def step_url(ref: steps.StepRef | None) -> str:
    if ref is None:
        return reverse("core:home")
    args = [ref.slug, ref.key] if ref.key else [ref.slug]
    return reverse("onboarding:step", args=args)


def _locate(household, slug: str, key) -> tuple[list[steps.StepRef], int]:
    refs = steps.sequence(household)
    for index, ref in enumerate(refs):
        if ref.slug == slug and ref.key == (str(key) if key else None):
            return refs, index
    raise Http404


@owner_only
def start(request: HttpRequest) -> HttpResponse:
    return redirect(step_url(steps.sequence(request.household)[0]))


@require_POST
@owner_only
def dismiss(request: HttpRequest) -> HttpResponse:
    """« Passer l'assistant » : rien n'est perdu, tout reste modifiable ailleurs."""
    services.mark_onboarded(request.household)
    return redirect("core:home")


@require_http_methods(["GET", "POST"])
@owner_only
def wizard(request: HttpRequest, slug: str, key=None) -> HttpResponse:
    handler = steps.REGISTRY.get(slug)
    if handler is None:
        raise Http404
    household = request.household
    refs, index = _locate(household, slug, key)
    ref = refs[index]
    following = refs[index + 1] if index + 1 < len(refs) else None
    previous = refs[index - 1] if index > 0 else None
    if request.method == "POST":
        response = _handle_post(request, handler, ref, following)
        if response is not None:
            return response
        refs, index = _locate(household, slug, key)  # la séquence a pu changer (convives)
    context = {
        "handler": handler,
        "ref": ref,
        "diner": ref.diner,
        "title": handler.title(ref.diner),
        "form": handler.form(household, ref.diner, request.POST or None),
        "position": index + 1,
        "total": len(refs),
        "back_url": step_url(previous) if previous else None,
        "next_url": step_url(following),
        "summary": steps.summary(household) if handler.kind == "summary" else None,
        "diners": Diner.objects.for_household(household) if handler.kind == "diners" else None,
    }
    return render(request, f"onboarding/{handler.kind}.html", context)


def _handle_post(request, handler, ref, following) -> HttpResponse | None:
    action = request.POST.get("action", "save")
    household = request.household
    if handler.kind == "summary":
        services.mark_onboarded(household)
        target = "planner:new" if action == "menu" else "core:home"
        return redirect(target)
    if handler.kind == "diners":
        return _handle_diners(request, handler, ref)
    if action == "skip":
        return redirect(step_url(following))
    form = handler.form(household, ref.diner, request.POST)
    if form.is_valid():
        handler.save(household, ref.diner, form)
        return redirect(step_url(following))
    return None


def _handle_diners(request, handler, ref) -> HttpResponse | None:
    household = request.household
    if request.POST.get("action") == "remove":
        diner = get_object_or_404(
            Diner.objects.for_household(household), pk=request.POST.get("diner")
        )
        diner.delete()
        return redirect(step_url(ref))
    form = handler.form(household, None, request.POST)
    if form.is_valid():
        handler.save(household, None, form)
        messages.success(request, f"{form.cleaned_data['first_name']} a été ajouté.")
        return redirect(step_url(ref))
    return None
