"""Synchronisation des courses hors ligne : opérations idempotentes, dernier geste gagnant."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from apps.core.reference import Aisle

from . import services
from .models import ShoppingItem, ShoppingList

MAX_OPERATIONS = 200
MAX_CLOCK_SKEW = timedelta(minutes=5)  # un téléphone en avance ne doit pas figer une ligne
MAX_LABEL = 200
APPLIED, STALE, MISSING, INVALID = "applied", "stale", "missing", "invalid"


@dataclass(frozen=True)
class Operation:
    op_id: str
    kind: str
    item_id: uuid.UUID
    at: datetime
    checked: bool = False
    label: str = ""
    quantity: Decimal | None = None
    aisle: str = Aisle.MISC


def _timestamp(raw, now: datetime) -> datetime:
    """Millisecondes depuis 1970 envoyées par le client, bornées à l'heure du serveur."""
    moment = datetime.fromtimestamp(float(raw) / 1000, tz=UTC)
    return min(moment, now + MAX_CLOCK_SKEW)


def parse_operation(raw: object, now: datetime) -> Operation | None:
    """Une opération mal formée est ignorée, jamais une cause d'erreur 500."""
    if not isinstance(raw, dict):
        return None
    try:
        kind = raw["type"]
        item_id = uuid.UUID(str(raw["item"]))
        at = _timestamp(raw["ts"], now)
        quantity = raw.get("quantity")
        quantity = None if quantity in (None, "") else Decimal(str(quantity))
    except (KeyError, ValueError, TypeError, InvalidOperation, OverflowError, OSError):
        return None
    if kind not in {"set", "add", "remove"} or (quantity is not None and quantity < 0):
        return None
    label = str(raw.get("label", "")).strip()[:MAX_LABEL]
    aisle = raw.get("aisle", Aisle.MISC)
    if kind == "add" and (not label or aisle not in Aisle.values):
        return None
    return Operation(
        str(raw.get("id", "")), kind, item_id, at, bool(raw.get("checked")), label, quantity, aisle
    )


def _set_checked(item: ShoppingItem, operation: Operation) -> str:
    if item.checked_at is not None and operation.at < item.checked_at:
        return STALE  # un geste plus récent (autre appareil) a déjà été enregistré
    item.checked, item.checked_at = operation.checked, operation.at
    item.save(update_fields=["checked", "checked_at"])
    return APPLIED


def _add(shopping_list: ShoppingList, operation: Operation) -> str:
    existing = ShoppingItem.objects.filter(pk=operation.item_id).first()
    if existing is not None:
        return APPLIED if existing.shopping_list_id == shopping_list.pk else INVALID
    ShoppingItem.objects.create(
        pk=operation.item_id,
        shopping_list=shopping_list,
        key=f"manual:{operation.item_id}",
        label=operation.label,
        quantity=operation.quantity,
        aisle=operation.aisle,
        manual=True,
    )
    return APPLIED


def apply_operation(shopping_list: ShoppingList, operation: Operation) -> str:
    if operation.kind == "add":
        return _add(shopping_list, operation)
    item = shopping_list.items.filter(pk=operation.item_id).first()
    if item is None:
        return MISSING  # ligne supprimée par un recalcul : on abandonne en silence
    if operation.kind == "remove":
        services.remove_item(item)
        return APPLIED
    return _set_checked(item, operation)


def apply_operations(shopping_list: ShoppingList, raw_operations: list) -> list[dict]:
    """Rejoue la file du client dans l'ordre ; retourne un statut par opération."""
    now = timezone.now()
    results = []
    for raw in raw_operations[:MAX_OPERATIONS]:
        operation = parse_operation(raw, now)
        op_id = str(raw.get("id", "")) if isinstance(raw, dict) else ""
        status = INVALID if operation is None else apply_operation(shopping_list, operation)
        results.append({"id": op_id, "status": status})
    return results


def snapshot(shopping_list: ShoppingList) -> dict:
    """État actuel de la liste, renvoyé au client pour rafraîchir son affichage et son cache."""
    from .display import describe_quantity

    items = [
        {
            "id": str(item.pk),
            "label": item.label,
            "quantity": describe_quantity(
                item.quantity, item.unit, item.packs, item.pack_size, item.pack_label
            ),
            "checked": item.checked,
            "aisle": item.aisle,
            "manual": item.manual,
        }
        for item in shopping_list.items.filter(hidden=False)
    ]
    return {"items": items, "signature": shopping_list.signature}
