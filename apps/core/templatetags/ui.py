from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def icon(name: str, css: str = "") -> str:
    """Icône du sprite inline (components/icons.html), décorative donc masquée aux lecteurs."""
    classes = f"icon {css}".strip()
    return format_html(
        '<svg class="{}" aria-hidden="true" focusable="false"><use href="#i-{}"/></svg>',
        classes,
        name,
    )


@register.filter
def initial(value: object) -> str:
    text = str(value or "").strip()
    return text[:1].upper() if text else "?"
