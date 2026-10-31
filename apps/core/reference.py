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
