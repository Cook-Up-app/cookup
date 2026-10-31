"""Extraction d'une recette depuis une page (JSON-LD d'abord, via `recipe-scrapers`)."""

import html
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import nh3

from apps.catalog.dto import RecipeDTO
from apps.catalog.inference import infer_meal_types

from .exceptions import ParseFailed

DEFAULT_SERVINGS = 4
MAX_SERVINGS = 50
MAX_TAGS = 12
MAX_STEPS = 40
MAX_INGREDIENTS = 80


def clean_text(value: str) -> str:
    """Retire tout balisage (nh3) et décode les entités : texte brut sûr à stocker."""
    return html.unescape(nh3.clean(value or "", tags=set())).strip()


def _optional(getter: Callable[[], Any], default: Any = None) -> Any:
    """Un champ absent de la page n'est pas une erreur ; les autres exceptions remontent."""
    from recipe_scrapers._exceptions import (
        ElementNotFoundInHtml,
        FieldNotProvidedByWebsiteException,
        SchemaOrgException,
    )

    try:
        return getter()
    except (SchemaOrgException, ElementNotFoundInHtml, FieldNotProvidedByWebsiteException):
        return default


def _servings(raw: Any) -> int:
    match = re.search(r"\d+", str(raw or ""))
    value = int(match.group()) if match else DEFAULT_SERVINGS
    return value if 0 < value <= MAX_SERVINGS else DEFAULT_SERVINGS


def _safe_image(url: str | None) -> str:
    return url if url and urlsplit(url).scheme in {"http", "https"} else ""


def _as_strings(value: str | list[str] | None) -> list[str]:
    if not value:
        return []
    return [value] if isinstance(value, str) else [str(item) for item in value]


def _split_tags(*values: str | list[str] | None) -> list[str]:
    tags: list[str] = []
    for value in values:
        for text in _as_strings(value):
            for part in re.split(r"[,;]", clean_text(text)):
                tag = part.strip().lower()
                if tag and tag not in tags and len(tag) <= 40:
                    tags.append(tag)
    return tags[:MAX_TAGS]


def _rating(scraper) -> float | None:
    value = _optional(scraper.ratings)
    return float(value) if value else None


def source_ref_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.netloc}{parts.path}"[:300]


_TITLE_SUFFIX = re.compile(r"\s*:\s*la meilleure recette\s*$", re.IGNORECASE)


def _clean_title(raw: str) -> str:
    """Retire le slogan que Marmiton ajoute à tous ses titres."""
    return _TITLE_SUFFIX.sub("", clean_text(raw)).strip()


def parse_recipe_html(page: str, url: str, source: str) -> RecipeDTO:
    """Lève `ParseFailed` si la page n'expose pas de recette exploitable."""
    from recipe_scrapers import scrape_html
    from recipe_scrapers._exceptions import RecipeScrapersExceptions

    try:
        scraper = scrape_html(page, org_url=url, wild_mode=True)
        title = _clean_title(scraper.title())
        ingredients = [clean_text(line) for line in scraper.ingredients()]
        steps = [clean_text(step) for step in scraper.instructions_list()]
    except RecipeScrapersExceptions as error:
        raise ParseFailed("Aucune recette exploitable dans la page.") from error
    ingredients = [line for line in ingredients if line][:MAX_INGREDIENTS]
    steps = [step for step in steps if step][:MAX_STEPS]
    if not title or not ingredients:
        raise ParseFailed("Recette sans titre ou sans ingrédients.")
    category = " ".join(_as_strings(_optional(scraper.category, "")))
    tags = _split_tags(_optional(scraper.keywords, ""), category)
    return RecipeDTO(
        source=source,
        title=title,
        ingredient_lines=ingredients,
        steps=steps,
        source_ref=source_ref_of(url),
        url=url,
        image_url=_safe_image(_optional(scraper.image)),
        servings=_servings(_optional(scraper.yields)),
        prep_minutes=_optional(scraper.prep_time),
        cook_minutes=_optional(scraper.cook_time),
        tags=tags,
        meal_types=infer_meal_types(category, *tags),
        rating=_rating(scraper),
    )
