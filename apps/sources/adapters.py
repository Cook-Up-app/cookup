"""Adaptateurs de sources : import par URL (tout domaine autorisé) et Marmiton."""

import re
from urllib.parse import quote, urlsplit

from apps.catalog.dto import RecipeDTO
from apps.core.reference import RecipeSource

from .contracts import RawRecipe, RecipeStub, SearchQuery
from .exceptions import FetchRefused
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
