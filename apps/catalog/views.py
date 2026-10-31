from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_safe

from apps.core.reference import Allergen
from apps.sources.exceptions import SourceError, SourceUnavailable
from apps.sources.importer import (
    build_source_for,
    enqueue_recipe,
    run_recipe_job,
    source_key_for,
)
from apps.sources.models import ImportJob

from . import services
from .forms import ImportUrlForm, ManualRecipeForm, SearchForm
from .models import Recipe

IMPORTS_PER_HOUR = 20


@require_safe
def recipe_list(request: HttpRequest) -> HttpResponse:
    form = SearchForm(request.GET)
    filters = services.SearchFilters()
    if form.is_valid():
        data = form.cleaned_data
        filters = services.SearchFilters(
            query=data["q"],
            max_minutes=data["max_minutes"],
            source=data["source"],
            meal_type=data["meal_type"],
            cookeo_only=data["cookeo_only"],
        )
    page = Paginator(services.search_recipes(filters), services.PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    return render(request, "catalog/list.html", {"form": form, "page": page})


@require_safe
def recipe_detail(request: HttpRequest, pk) -> HttpResponse:
    recipe = get_object_or_404(Recipe.objects.prefetch_related("ingredients__ingredient"), pk=pk)
    allergens, uncertain = services.recipe_allergens(recipe)
    context = {
        "recipe": recipe,
        "allergens": [Allergen(code).label for code in allergens],
        "allergens_uncertain": uncertain,
    }
    return render(request, "catalog/detail.html", context)


def _import_quota_reached(user) -> bool:
    since = timezone.now() - timedelta(hours=1)
    return (
        ImportJob.objects.filter(requested_by=user, created_at__gte=since).count()
        >= IMPORTS_PER_HOUR
    )


@require_http_methods(["GET", "POST"])
def recipe_import(request: HttpRequest) -> HttpResponse:
    form = ImportUrlForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _import_quota_reached(request.user):
            messages.error(request, "Trop d'imports récents : réessayez dans une heure.")
            return redirect("catalog:import")
        return _run_import(request, form.cleaned_data["url"])
    recent = ImportJob.objects.filter(requested_by=request.user).order_by("-created_at")[:10]
    return render(request, "catalog/import.html", {"form": form, "recent": recent})


def _run_import(request: HttpRequest, url: str) -> HttpResponse:
    source_key = source_key_for(url)
    job, _ = enqueue_recipe(source_key, url, request.user)
    try:
        finished = run_recipe_job(job, build_source_for(source_key))
    except SourceUnavailable as error:
        messages.error(request, f"Source indisponible : {error}")
    except SourceError as error:
        messages.error(request, f"Import impossible : {error}")
    else:
        if finished.recipe_id:
            messages.success(request, "Recette importée." if not finished.error else finished.error)
            return redirect("catalog:detail", pk=finished.recipe_id)
        messages.error(request, finished.error or "Import impossible.")
    return redirect("catalog:import")


@require_http_methods(["GET", "POST"])
def recipe_create(request: HttpRequest) -> HttpResponse:
    form = ManualRecipeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        recipe, created = services.save_recipe(form.to_dto())
        if not created:
            messages.info(request, "Cette recette existe déjà au catalogue.")
        return redirect("catalog:detail", pk=recipe.pk)
    return render(request, "catalog/create.html", {"form": form})
