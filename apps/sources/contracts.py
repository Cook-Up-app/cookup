"""Contrats des sources (SPEC section 14 : petites interfaces séparées, ségrégation)."""

from dataclasses import dataclass
from typing import Protocol

from apps.catalog.dto import RecipeDTO


@dataclass(frozen=True)
class SearchQuery:
    text: str


@dataclass(frozen=True)
class RecipeStub:
    url: str
    title: str = ""


@dataclass(frozen=True)
class RawRecipe:
    url: str
    html: str


class Searchable(Protocol):
    def search(self, query: SearchQuery) -> list[RecipeStub]: ...


class Fetchable(Protocol):
    def fetch(self, ref: str) -> RawRecipe: ...


class Discoverable(Protocol):
    """Source qui sait lister des recettes sans recherche (sitemap déclaré dans robots.txt)."""

    def discover(self, seed: int, limit: int) -> list[RecipeStub]: ...


class Parsable(Protocol):
    def parse(self, raw: RawRecipe) -> RecipeDTO: ...
