"""Enregistrement et recherche de recettes : normalisation, déduplication, plein texte."""

import hashlib
from dataclasses import dataclass
from decimal import Decimal

from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    SearchVector,
    TrigramSimilarity,
)
from django.db import transaction
from django.db.models import F, Q, QuerySet
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.households.models import Equipment

from .dto import RecipeDTO
from .matching import IngredientIndex
from .models import Ingredient, Recipe, RecipeEquipment, RecipeIngredient
from .normalization import ParsedLine, parse_line, split_compound, to_base
from .text import fold, stem_key

TRIGRAM_THRESHOLD = 0.5
SEARCH_LANGUAGE = "french"
PAGE_SIZE = 20


def load_index() -> IngredientIndex:
    rows = Ingredient.objects.values_list("id", "name", "aliases")
    return IngredientIndex([(pk, name, aliases) for pk, name, aliases in rows])


@dataclass(frozen=True)
class NormalizedLine:
    parsed: ParsedLine
    ingredient_id: int | None
    needs_review: bool


def _trigram_match(name: str) -> int | None:
    best = (
        Ingredient.objects.annotate(similarity=TrigramSimilarity("normalized_name", stem_key(name)))
        .filter(similarity__gte=TRIGRAM_THRESHOLD)
        .order_by("-similarity")
        .first()
    )
    return best.pk if best else None


def normalize_line(line: str, index: IngredientIndex) -> NormalizedLine:
    """Exact, puis contenu, puis similarité ; tout ce qui n'est pas exact est à vérifier."""
    parsed = parse_line(line)
    match = index.find(parsed.name)
    if match is not None:
        return NormalizedLine(parsed, match.ingredient_id, needs_review=not match.exact)
    fallback = _trigram_match(parsed.name) if parsed.name else None
    return NormalizedLine(parsed, fallback, needs_review=True)


def normalize_lines(lines: list[str], index: IngredientIndex) -> list[NormalizedLine]:
    expanded = [part for line in lines for part in split_compound(line)]
    return [normalize_line(line, index) for line in expanded if line.strip()]


def fingerprint(title: str, lines: list[NormalizedLine]) -> str:
    """Empreinte du contenu : titre normalisé et ingrédients triés (déduplication)."""
    names = sorted(stem_key(line.parsed.name) for line in lines)
    return hashlib.sha256(f"{stem_key(title)}|{'|'.join(names)}".encode()).hexdigest()


def _search_text(dto: RecipeDTO, lines: list[NormalizedLine], names: dict[int, str]) -> str:
    parts = [dto.title, *dto.tags]
    for line in lines:
        parts.append(names.get(line.ingredient_id) or line.parsed.name)
    return fold(" ".join(parts))


def _ingredient_rows(recipe: Recipe, lines: list[NormalizedLine]) -> list[RecipeIngredient]:
    rows = []
    for position, line in enumerate(lines):
        parsed = line.parsed
        base_quantity, base_unit = to_base(parsed.quantity, parsed.unit)
        rows.append(
            RecipeIngredient(
                recipe=recipe,
                ingredient_id=line.ingredient_id,
                position=position,
                raw_text=parsed.raw_text[:300],
                quantity=parsed.quantity,
                unit=parsed.unit.code if parsed.unit else "",
                base_quantity=base_quantity,
                base_unit=base_unit,
                is_optional=parsed.is_optional,
                needs_review=line.needs_review,
            )
        )
    return rows


def _link_equipment(recipe: Recipe, dto: RecipeDTO) -> None:
    required = {code: True for code in dto.required_equipment}
    required.update({code: False for code in dto.optional_equipment if code not in required})
    known = Equipment.objects.filter(code__in=required)
    RecipeEquipment.objects.bulk_create(
        RecipeEquipment(recipe=recipe, equipment=item, required=required[item.code])
        for item in known
    )


@transaction.atomic
def save_recipe(dto: RecipeDTO, index: IngredientIndex | None = None) -> tuple[Recipe, bool]:
    """Écrit une recette ; retourne (recette, créée). Un doublon renvoie l'existante."""
    index = index or load_index()
    lines = normalize_lines(dto.ingredient_lines, index)
    digest = fingerprint(dto.title, lines)
    existing = Recipe.objects.filter(content_fingerprint=digest).first()
    if existing is None and dto.source_ref:
        existing = Recipe.objects.filter(source=dto.source, source_ref=dto.source_ref).first()
    if existing is not None:
        return existing, False
    names = dict(Ingredient.objects.values_list("id", "name"))
    recipe = Recipe.objects.create(
        source=dto.source,
        source_ref=dto.source_ref,
        url=dto.url,
        title=dto.title[:200],
        image_url=dto.image_url,
        servings=dto.servings,
        prep_minutes=dto.prep_minutes,
        cook_minutes=dto.cook_minutes,
        difficulty=dto.difficulty,
        cost_level=dto.cost_level,
        steps=dto.steps,
        tags=dto.tags,
        meal_types=dto.meal_types,
        cookeo_compatible=dto.cookeo_compatible,
        cookeo_program=dto.cookeo_program,
        needs_review=any(line.needs_review or line.ingredient_id is None for line in lines),
        content_fingerprint=digest,
        fetched_at=timezone.now() if dto.url else None,
        search_text=_search_text(dto, lines, names),
    )
    RecipeIngredient.objects.bulk_create(_ingredient_rows(recipe, lines))
    _link_equipment(recipe, dto)
    Recipe.objects.filter(pk=recipe.pk).update(
        search_vector=SearchVector("search_text", config=SEARCH_LANGUAGE)
    )
    return recipe, True


@dataclass(frozen=True)
class SearchFilters:
    query: str = ""
    max_minutes: int | None = None
    source: str = ""
    meal_type: str = ""
    tag: str = ""
    cookeo_only: bool = False


def search_recipes(filters: SearchFilters) -> QuerySet[Recipe]:
    """Plein texte français (accents repliés), tolérant aux fautes de frappe (trigrammes)."""
    queryset = Recipe.objects.all()
    if filters.query.strip():
        folded = fold(filters.query)
        query = SearchQuery(folded, config=SEARCH_LANGUAGE, search_type="websearch")
        queryset = (
            queryset.annotate(rank=SearchRank(F("search_vector"), query))
            .filter(Q(search_vector=query) | Q(search_text__trigram_word_similar=folded))
            .order_by("-rank", "title")
        )
    if filters.max_minutes:
        queryset = queryset.annotate(
            total=Coalesce("prep_minutes", 0) + Coalesce("cook_minutes", 0)
        ).filter(total__lte=filters.max_minutes, total__gt=0)
    if filters.source:
        queryset = queryset.filter(source=filters.source)
    if filters.meal_type:
        queryset = queryset.filter(meal_types__contains=[filters.meal_type])
    if filters.tag:
        queryset = queryset.filter(tags__contains=[filters.tag])
    if filters.cookeo_only:
        queryset = queryset.filter(cookeo_compatible=True)
    return queryset


def quantity_label(value: Decimal | None) -> str:
    """Affichage d'une quantité sans zéros inutiles (1,5 ; 200)."""
    if value is None:
        return ""
    text = format(value.normalize(), "f").replace(".", ",")
    return text


def recipe_allergens(recipe: Recipe) -> tuple[list[str], bool]:
    """Allergènes des ingrédients reconnus, et si un ingrédient reste inconnu ou non confirmé."""
    found: set[str] = set()
    uncertain = False
    for line in recipe.ingredients.all():
        ingredient = line.ingredient
        if ingredient is None or line.needs_review or not ingredient.allergens_reviewed:
            uncertain = True
        if ingredient is not None:
            found.update(ingredient.allergens)
    return sorted(found), uncertain
