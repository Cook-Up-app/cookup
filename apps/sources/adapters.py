"""Adaptateurs de sources : import par URL (tout domaine autorisé) et Marmiton."""

import random
import re
from dataclasses import replace
from urllib.parse import quote, urlsplit

from apps.catalog.dto import RecipeDTO
from apps.catalog.text import fold
from apps.core.reference import RecipeSource

from .contracts import RawRecipe, RecipeStub, SearchQuery
from .exceptions import FetchRefused, ParseFailed
from .http import PoliteFetcher
from .parsing import parse_recipe_html
from .registry import register

MARMITON_HOST = "www.marmiton.org"
MARMITON_SEARCH = f"https://{MARMITON_HOST}/recettes/recherche.aspx?aqt="
MARMITON_RECIPE_PATH = re.compile(r"^/recettes/recette_[\w-]+_\d+\.aspx$")
_RECIPE_LINK = re.compile(
    r'href="((?:https://www\.marmiton\.org)?/recettes/recette_[\w-]+_\d+\.aspx)"'
)
MAX_SEARCH_RESULTS = 12


@register(RecipeSource.URL_IMPORT)
class UrlImportSource:
    """Importe une page de recette dont le domaine est autorisé ; ne sait pas chercher."""

    key = RecipeSource.URL_IMPORT.value

    def __init__(self, fetcher: PoliteFetcher) -> None:
        self._fetcher = fetcher

    def fetch(self, ref: str) -> RawRecipe:
        result = self._fetcher.get(ref)
        return RawRecipe(url=result.url, html=result.text)

    def parse(self, raw: RawRecipe) -> RecipeDTO:
        return parse_recipe_html(raw.html, raw.url, self.key)


@register(RecipeSource.MARMITON)
class MarmitonSource(UrlImportSource):
    """Ajoute la recherche : première page de `recherche.aspx?aqt=…` seulement.

    Le robots.txt de Marmiton interdit la pagination (`page`, `start`) et les filtres (`type`) :
    on ne demande donc jamais que cette page, et on la fait varier par la requête.
    """

    key = RecipeSource.MARMITON.value

    def search(self, query: SearchQuery) -> list[RecipeStub]:
        result = self._fetcher.get(MARMITON_SEARCH + quote(query.text.strip()))
        urls: list[str] = []
        for link in _RECIPE_LINK.findall(result.text):
            url = link if link.startswith("https://") else f"https://{MARMITON_HOST}{link}"
            if url not in urls:
                urls.append(url)
        return [RecipeStub(url) for url in urls[:MAX_SEARCH_RESULTS]]

    def fetch(self, ref: str) -> RawRecipe:
        if not MARMITON_RECIPE_PATH.match(urlsplit(ref).path):
            raise FetchRefused("Ce n'est pas une page de recette Marmiton.")
        return super().fetch(ref)


MOULINEX_HOST = "www.moulinex.fr"
MOULINEX_SITEMAP = f"https://{MOULINEX_HOST}/Recipe-fr_fr-EUR.xml"
MOULINEX_RECIPE_PATH = re.compile(r"^/(?:recette|recipe)/detail/[A-Z]+/.+/\d+$")
_SITEMAP_LOC = re.compile(r"<loc>([^<]+)</loc>")
_HTML_LANG = re.compile(r"<html[^>]*\blang=\"([a-zA-Z]{2})")
SITEMAP_PREFIX_BYTES = 400_000  # le début du sitemap suffit : on n'en lit jamais plus


@register(RecipeSource.MOULINEX)
class MoulinexSource(UrlImportSource):
    """moulinex.fr : découverte par sitemap (sa recherche est interdite par robots.txt).

    Par prudence vis-à-vis des conditions du Groupe SEB, seul le strict nécessaire est conservé :
    ingrédients, durée, portions et lien vers la page d'origine ; ni étapes ni images.
    """

    key = RecipeSource.MOULINEX.value

    def discover(self, seed: int, limit: int) -> list[RecipeStub]:
        page = self._fetcher.get(MOULINEX_SITEMAP, max_bytes=SITEMAP_PREFIX_BYTES, truncate=True)
        urls = [u for u in _SITEMAP_LOC.findall(page.text) if self._is_recipe(u)]
        random.Random(seed).shuffle(urls)  # noqa: S311 - tirage reproductible, pas de crypto
        return [RecipeStub(url) for url in urls[:limit]]

    @staticmethod
    def _is_recipe(url: str) -> bool:
        parts = urlsplit(url)
        return parts.netloc == MOULINEX_HOST and bool(MOULINEX_RECIPE_PATH.match(parts.path))

    def fetch(self, ref: str) -> RawRecipe:
        if not self._is_recipe(ref):
            raise FetchRefused("Ce n'est pas une page de recette Moulinex.")
        return super().fetch(ref)

    def parse(self, raw: RawRecipe):
        language = _HTML_LANG.search(raw.html)
        if language is None or language.group(1).lower() != "fr":
            raise ParseFailed("Page non française : ignorée.")
        dto = super().parse(raw)
        text = fold(" ".join([dto.title, *dto.tags, *dto.steps]))
        return replace(
            dto,
            steps=[],
            image_url="",
            cookeo_compatible="cookeo" in text,
            tags=[*dto.tags, "moulinex"][:12],
        )
