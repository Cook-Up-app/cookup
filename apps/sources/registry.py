"""Registre des sources : ajouter une source = enregistrer une classe (ouvert/fermé)."""

from collections.abc import Callable
from typing import Any

from .exceptions import SourceUnavailable

_FACTORIES: dict[str, Callable[..., Any]] = {}


def register(key: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(factory: Callable[..., Any]) -> Callable[..., Any]:
        _FACTORIES[key] = factory
        return factory

    return decorator


def build_source(key: str, **dependencies: Any) -> Any:
    try:
        return _FACTORIES[key](**dependencies)
    except KeyError as error:
        raise SourceUnavailable(f"Source inconnue : {key}") from error


def registered_keys() -> list[str]:
    return sorted(_FACTORIES)
