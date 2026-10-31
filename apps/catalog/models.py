import uuid

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.querysets import HouseholdQuerySet
from apps.core.reference import Aisle, Allergen, MealType, RecipeSource


class Ingredient(models.Model):
    """Ingrédient canonique auquel les textes libres des recettes sont rattachés."""

    name = models.CharField("nom", max_length=100, unique=True)
    normalized_name = models.CharField(max_length=100, unique=True, editable=False)
    aisle = models.CharField(max_length=20, choices=Aisle.choices, default=Aisle.MISC)
    allergens = ArrayField(
        models.CharField(max_length=20, choices=Allergen.choices), default=list, blank=True
    )
    # Faux tant qu'un humain n'a pas confirmé la liste d'allergènes : le moteur échoue côté sûr.
    allergens_reviewed = models.BooleanField(default=False)
    aliases = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    default_unit = models.CharField(max_length=20, blank=True)
    density_g_per_ml = models.DecimalField(max_digits=5, decimal_places=3, null=True, blank=True)
    is_staple = models.BooleanField("produit de base", default=False)
    # Dérivés du nom et des allergènes (voir `traits`) : régimes et groupe de protéine.
    diet_flags = ArrayField(models.CharField(max_length=10), default=list, blank=True)
    protein = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            GinIndex(
                fields=["normalized_name"], opclasses=["gin_trgm_ops"], name="ingredient_trgm_idx"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Recipe(models.Model):
    """Recette du catalogue, partagé entre foyers."""

    class Difficulty(models.TextChoices):
        EASY = "easy", "Facile"
        MEDIUM = "medium", "Moyen"
        HARD = "hard", "Difficile"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=20, choices=RecipeSource.choices)
    source_ref = models.CharField(max_length=300, blank=True)
    url = models.URLField(max_length=500, blank=True)
    title = models.CharField("titre", max_length=200)
    image_url = models.URLField(max_length=500, blank=True)
    servings = models.PositiveSmallIntegerField("portions", default=4)
    prep_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    cook_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    difficulty = models.CharField(max_length=10, choices=Difficulty.choices, blank=True)
    cost_level = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(3)]
    )
    steps = models.JSONField(default=list, blank=True)
    tags = ArrayField(models.CharField(max_length=40), default=list, blank=True)
    meal_types = ArrayField(
        models.CharField(max_length=10, choices=MealType.choices), default=list, blank=True
    )
    cookeo_compatible = models.BooleanField(default=False)
    cookeo_program = models.JSONField(default=dict, blank=True)
    needs_review = models.BooleanField(default=False)
    content_fingerprint = models.CharField(max_length=64, unique=True)
    fetched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    search_text = models.TextField(blank=True, editable=False)
    search_vector = SearchVectorField(null=True, editable=False)

    class Meta:
        ordering = ["title"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_ref"],
                condition=~models.Q(source_ref=""),
                name="recipe_source_ref_unique",
            ),
        ]
        indexes = [
            GinIndex(fields=["search_vector"], name="recipe_search_vector_idx"),
            GinIndex(fields=["search_text"], opclasses=["gin_trgm_ops"], name="recipe_trgm_idx"),
            models.Index(fields=["source", "created_at"], name="recipe_source_created_idx"),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def total_minutes(self) -> int | None:
        parts = [m for m in (self.prep_minutes, self.cook_minutes) if m is not None]
        return sum(parts) if parts else None


class RecipeIngredient(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="ingredients")
    ingredient = models.ForeignKey(
        Ingredient, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    position = models.PositiveSmallIntegerField(default=0)
    raw_text = models.CharField(max_length=300)  # conservé pour re-normaliser plus tard
    quantity = models.DecimalField(max_digits=9, decimal_places=3, null=True, blank=True)
    unit = models.CharField(max_length=20, blank=True)
    base_quantity = models.DecimalField(max_digits=9, decimal_places=3, null=True, blank=True)
    base_unit = models.CharField(max_length=20, blank=True)
    is_optional = models.BooleanField(default=False)
    needs_review = models.BooleanField(default=False)

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return self.raw_text


class RecipeEquipment(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="equipment")
    equipment = models.ForeignKey(
        "households.Equipment", on_delete=models.CASCADE, related_name="+"
    )
    required = models.BooleanField("obligatoire", default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["recipe", "equipment"], name="recipe_equipment_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.recipe} : {self.equipment}"


class RecipeFeedback(models.Model):
    """Avis d'un foyer sur une recette : favori, exclusion, note (alimente le moteur de menus)."""

    household = models.ForeignKey(
        "households.Household", on_delete=models.CASCADE, related_name="recipe_feedback"
    )
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="feedback")
    favorite = models.BooleanField(default=False)
    excluded = models.BooleanField(default=False)
    rating = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    last_served_on = models.DateField(null=True, blank=True)

    objects = HouseholdQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["household", "recipe"], name="feedback_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.household} / {self.recipe}"
