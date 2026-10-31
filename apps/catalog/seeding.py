"""Chargement du catalogue d'ingrédients (idempotent)."""

from decimal import Decimal

from apps.core.reference import Aisle

from .ingredient_catalog import AISLES, ALLERGENS, CATALOG
from .models import Ingredient
from .text import stem_key
from .traits import diet_flags, protein_group

PARTS = 6


def _parse_line(line: str) -> dict:
    parts = (line.split("|") + [""] * PARTS)[:PARTS]
    name, aisle, allergens, flags, aliases, density = (part.strip() for part in parts)
    return {
        "name": name,
        "aisle": AISLES.get(aisle, Aisle.MISC) if aisle else Aisle.MISC,
        "allergens": [ALLERGENS[code] for code in allergens.split(",") if code],
        "is_staple": "s" in flags,
        "allergens_reviewed": "u" not in flags,
        "aliases": [alias.strip() for alias in aliases.split(";") if alias.strip()],
        "density_g_per_ml": Decimal(density) if density else None,
    }


def parse_catalog() -> list[dict]:
    return [_parse_line(line) for line in CATALOG.splitlines() if line.strip()]


def seed_ingredients() -> int:
    """Crée ou met à jour les ingrédients de départ ; retourne leur nombre."""
    entries = parse_catalog()
    for entry in entries:
        name = entry.pop("name")
        entry["diet_flags"] = diet_flags(name, entry["aisle"], entry["allergens"])
        entry["protein"] = protein_group(name, entry["allergens"])
        Ingredient.objects.update_or_create(
            normalized_name=stem_key(name), defaults={"name": name, **entry}
        )
    return len(entries)
