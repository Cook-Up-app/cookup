"""Tables de référence partagées : source unique des allergènes, régimes et équipements."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Allergen(models.TextChoices):
    """Les 14 allergènes à déclaration obligatoire dans l'UE (règlement 1169/2011)."""

    GLUTEN = "gluten", _("Céréales contenant du gluten")
    CRUSTACEANS = "crustaceans", _("Crustacés")
    EGGS = "eggs", _("Œufs")
    FISH = "fish", _("Poissons")
    PEANUTS = "peanuts", _("Arachides")
    SOY = "soy", _("Soja")
    MILK = "milk", _("Lait")
    TREE_NUTS = "tree_nuts", _("Fruits à coque")
    CELERY = "celery", _("Céleri")
    MUSTARD = "mustard", _("Moutarde")
    SESAME = "sesame", _("Graines de sésame")
    SULPHITES = "sulphites", _("Anhydride sulfureux et sulfites")
    LUPIN = "lupin", _("Lupin")
    MOLLUSCS = "molluscs", _("Mollusques")


class Diet(models.TextChoices):
    VEGETARIAN = "vegetarian", _("Végétarien")
    VEGAN = "vegan", _("Végétalien")
    NO_PORK = "no_pork", _("Sans porc")
    HALAL = "halal", _("Halal")
    KOSHER = "kosher", _("Casher")
    PESCATARIAN = "pescatarian", _("Pescétarien")


class Equipment(models.TextChoices):
    """Équipements de cuisine ; `COOKEO` active le mode Cookeo (jalon M5)."""

    COOKEO = "cookeo_yy5449fb", _("Cookeo YY5449FB")
    OVEN = "oven", _("Four")
    HOB = "hob", _("Plaques de cuisson")
    MICROWAVE = "microwave", _("Micro-ondes")
    BLENDER = "blender", _("Mixeur")
    FOOD_PROCESSOR = "food_processor", _("Robot de cuisine")
    AIR_FRYER = "air_fryer", _("Friteuse à air")
    DUTCH_OVEN = "dutch_oven", _("Cocotte")


class Aisle(models.TextChoices):
    """Rayons, dans l'ordre d'un parcours de magasin type (SPEC section 8)."""

    FRUITS_VEGETABLES = "fruits_vegetables", _("Fruits et légumes")
    BUTCHER_FISH = "butcher_fish", _("Boucherie et poissonnerie")
    DAIRY = "dairy", _("Crèmerie")
    BAKERY = "bakery", _("Boulangerie")
    SAVORY_GROCERY = "savory_grocery", _("Épicerie salée")
    SWEET_GROCERY = "sweet_grocery", _("Épicerie sucrée")
    CONDIMENTS_SPICES = "condiments_spices", _("Condiments et épices")
    FROZEN = "frozen", _("Surgelés")
    DRINKS = "drinks", _("Boissons")
    MISC = "misc", _("Divers")


class MealType(models.TextChoices):
    BREAKFAST = "breakfast", _("Petit-déjeuner")
    LUNCH = "lunch", _("Déjeuner")
    DINNER = "dinner", _("Dîner")
    SNACK = "snack", _("Collation")
    DESSERT = "dessert", _("Dessert")


# Ordre chronologique des repas d'une journée (le dessert suit le repas principal).
MEAL_ORDER = (
    MealType.BREAKFAST,
    MealType.LUNCH,
    MealType.SNACK,
    MealType.DINNER,
    MealType.DESSERT,
)


class RecipeSource(models.TextChoices):
    """Clés des sources de recettes (voir `apps.sources`)."""

    URL_IMPORT = "url_import", _("Import par URL")
    MARMITON = "marmiton", _("Marmiton")
    MOULINEX = "moulinex", _("Moulinex")
    MANUAL = "manual", _("Saisie manuelle")
    AI = "ai", _("Générée par IA")
    STARTER = "starter", _("Recette originale du jeu de départ")
