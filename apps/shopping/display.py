"""Libellés de quantités pour l'affichage (« 2 boîtes de 400 g », « 1,5 kg », « 3 pièces »)."""

from decimal import Decimal

THOUSAND = Decimal(1000)
UNIT_NAMES = {"pièce": "", "g": "g", "ml": "ml"}


def _number(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text.replace(".", ",")


def _measure(quantity: Decimal, unit: str) -> str:
    if unit == "g" and quantity >= THOUSAND:
        return f"{_number(quantity / THOUSAND)} kg"
    if unit == "ml" and quantity >= THOUSAND:
        return f"{_number(quantity / THOUSAND)} l"
    suffix = UNIT_NAMES.get(unit, unit)
    return f"{_number(quantity)} {suffix}".strip()


def describe_quantity(
    quantity: Decimal | None,
    unit: str,
    packs: int | None,
    pack_size: Decimal | None,
    pack_label: str,
) -> str:
    """Texte de quantité d'une ligne ; vide si la ligne n'a pas de quantité."""
    if quantity is None:
        return ""
    if packs and pack_size and pack_label:
        plural = "s" if packs > 1 else ""
        pack = _measure(pack_size, unit)
        return f"{packs} {pack_label}{plural} de {pack} (≈ {_measure(quantity, unit)})"
    return _measure(quantity, unit)
