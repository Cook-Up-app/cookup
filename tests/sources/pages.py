"""Pages de test fabriquées pour le projet (aucun contenu de tiers)."""

import json
from html import escape


def recipe_page(
    title: str = "Gratin de courgettes",
    ingredients: tuple[str, ...] = (
        "3 courgettes",
        "20 cl de crème liquide",
        "100 g de gruyère râpé",
    ),
    steps: tuple[str, ...] = ("Couper les courgettes.", "Enfourner 30 minutes."),
    rating: float | None = 4.6,
    category: str = "Plat principal",
    image: str = "https://images.example.test/gratin.jpg",
    servings: str = "4 personnes",
) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": title,
        "image": image,
        "recipeCategory": category,
        "keywords": "gratin, légumes",
        "recipeYield": servings,
        "prepTime": "PT15M",
        "cookTime": "PT30M",
        "totalTime": "PT45M",
        "recipeIngredient": list(ingredients),
        "recipeInstructions": [{"@type": "HowToStep", "text": step} for step in steps],
    }
    if rating is not None:
        data["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": rating,
            "ratingCount": 80,
        }
    payload = json.dumps(data).replace("</", "<\\/")
    return (
        f"<html><head><title>{escape(title)}</title>"
        f'<script type="application/ld+json">{payload}</script></head><body></body></html>'
    )


def search_page(*slugs: str) -> str:
    links = "".join(f'<a href="/recettes/recette_{slug}.aspx">x</a>' for slug in slugs)
    return f'<html><body>{links}<a href="/mon-espace/x">y</a></body></html>'
