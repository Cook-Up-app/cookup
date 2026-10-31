from django import template

from apps.shopping.display import describe_quantity

register = template.Library()


@register.filter
def quantity_text(item) -> str:
    return describe_quantity(item.quantity, item.unit, item.packs, item.pack_size, item.pack_label)
