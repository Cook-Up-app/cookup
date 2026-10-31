from django.core.management.base import BaseCommand

from apps.catalog.seeding import seed_ingredients
from apps.catalog.services import renormalize_recipes
from apps.catalog.starter import load_starter_recipes


class Command(BaseCommand):
    help = "Charge les ingrédients puis les recettes originales du jeu de départ (idempotent)."

    def handle(self, *args, **options) -> None:
        self.stdout.write(f"Ingrédients : {seed_ingredients()}")
        created, existing = load_starter_recipes()
        self.stdout.write(f"Recettes : {created} créées, {existing} déjà présentes")
        self.stdout.write(f"Lignes renormalisées pour {renormalize_recipes()} recettes")
