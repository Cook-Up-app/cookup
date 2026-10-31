"""Lecture typée des variables d'environnement (source unique pour les réglages)."""

import os

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_VALUES


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw is None else int(raw)


def env_list(name: str, default: tuple[str, ...] = ()) -> list[str]:
    """Liste séparée par des virgules ; les éléments vides sont ignorés."""
    raw = os.environ.get(name)
    if raw is None:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_required(name: str) -> str:
    """Variable obligatoire : échoue au démarrage plutôt qu'en pleine requête."""
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"Variable d'environnement obligatoire manquante : {name}")
    return value
