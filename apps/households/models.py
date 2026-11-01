import uuid

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.querysets import HouseholdQuerySet
from apps.core.reference import Allergen, Cuisine, Diet, FoodGroup, MealType

from . import restrictions

WEIGHT_CRITERIA = (
    "taste", "style", "rating", "freshness", "diversity", "antiwaste", "budget", "season",
)  # fmt: skip
MAX_WEIGHT = 100


def validate_weights(value: dict) -> None:
    """Poids du score souple : critères connus, entiers de 0 à 100."""
    unknown = set(value) - set(WEIGHT_CRITERIA)
    if unknown or not all(isinstance(w, int) and 0 <= w <= MAX_WEIGHT for w in value.values()):
        raise ValidationError("Poids invalides.")


class HouseholdManagerQuerySet(models.QuerySet):
    def for_user(self, user) -> "HouseholdManagerQuerySet":
        return self.filter(memberships__user=user)


class Household(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField("nom", max_length=100)
    default_servings = models.PositiveSmallIntegerField("portions par défaut", default=4)
    week_start_day = models.PositiveSmallIntegerField(
        "jour de début de semaine", default=0, help_text="0 = lundi … 6 = dimanche"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = HouseholdManagerQuerySet.as_manager()

    def __str__(self) -> str:
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Propriétaire"
        MEMBER = "member", "Membre"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = HouseholdQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "household"], name="membership_unique"),
        ]
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.user} @ {self.household} ({self.role})"

    @property
    def is_owner(self) -> bool:
        return self.role == self.Role.OWNER


class Invitation(models.Model):
    """Invitation à usage unique ; seul le hachage du jeton est stocké."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # vide = n'expire jamais
    used_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = HouseholdQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Invitation de {self.email}"


class Diner(models.Model):
    """Convive : une personne à table, avec ou sans compte de connexion."""

    class AgeGroup(models.TextChoices):
        ADULT = "adult", "Adulte"
        CHILD = "child", "Enfant"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="diners")
    first_name = models.CharField("prénom", max_length=60)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    age_group = models.CharField(max_length=10, choices=AgeGroup.choices, default=AgeGroup.ADULT)
    diets = ArrayField(
        models.CharField(max_length=20, choices=Diet.choices), default=list, blank=True
    )

    objects = HouseholdQuerySet.as_manager()

    class Meta:
        ordering = ["first_name"]

    def __str__(self) -> str:
        return self.first_name


class RestrictionQuerySet(HouseholdQuerySet):
    household_field = "diner__household"


class DinerRestriction(models.Model):
    """Allergie stricte (contrainte dure), intolérance ou aliment évité."""

    class Severity(models.TextChoices):
        STRICT_ALLERGY = "strict_allergy", "Allergie stricte"
        INTOLERANCE = "intolerance", "Intolérance"
        AVOID = "avoid", "À éviter"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    diner = models.ForeignKey(Diner, on_delete=models.CASCADE, related_name="restrictions")
    allergen = models.CharField(max_length=20, choices=Allergen.choices, blank=True)
    food_group = models.CharField(max_length=20, choices=FoodGroup.choices, blank=True)
    ingredient_name = models.CharField("autre ingrédient", max_length=100, blank=True)
    severity = models.CharField(
        max_length=20, choices=Severity.choices, default=Severity.STRICT_ALLERGY
    )

    objects = RestrictionQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(allergen="") | ~Q(food_group="") | ~Q(ingredient_name=""),
                name="restriction_has_target",
            ),
        ]

    def __str__(self) -> str:
        return self.label

    @property
    def label(self) -> str:
        if self.allergen:
            return str(Allergen(self.allergen).label)
        if self.food_group:
            return str(FoodGroup(self.food_group).label)
        return self.ingredient_name

    @property
    def detail(self) -> str:
        """Ce que la restriction exclut concrètement, pour que la saisie soit vérifiable."""
        if self.food_group:
            return f"Exclut : {restrictions.group_examples(self.food_group)}"
        if self.ingredient_name and not self.allergen:
            return "Texte libre : recherché dans le texte des recettes"
        return ""

    @property
    def coverage(self) -> restrictions.Coverage:
        return restrictions.coverage(self.allergen, self.food_group, self.ingredient_name)


class Equipment(models.Model):
    """Catalogue fixe des équipements, alimenté par migration depuis `core.reference`."""

    code = models.CharField(max_length=40, primary_key=True)
    label = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.label


class HouseholdEquipment(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="equipment")
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="+")

    objects = HouseholdQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["household", "equipment"], name="household_equipment_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.household} : {self.equipment}"


def default_meals() -> list[str]:
    return ["lunch", "dinner"]


class HouseholdSettings(models.Model):
    """Réglages du moteur de menus ; les poids sont validés par `validate_weights`."""

    class SourceMode(models.TextChoices):
        CLASSIC = "classic", "Classique"
        COOKEO = "cookeo", "Cookeo"
        MIXED = "mixed", "Mixte"

    household = models.OneToOneField(Household, on_delete=models.CASCADE, related_name="settings")
    meals = ArrayField(
        models.CharField(max_length=10, choices=MealType.choices), default=default_meals
    )
    max_minutes_weekday = models.PositiveSmallIntegerField("temps max en semaine (min)", default=45)
    max_minutes_weekend = models.PositiveSmallIntegerField(
        "temps max le week-end (min)", default=90
    )
    budget_level = models.PositiveSmallIntegerField(
        "budget (1 à 3)", default=2, validators=[MinValueValidator(1), MaxValueValidator(3)]
    )
    leftover_weekdays = ArrayField(
        models.PositiveSmallIntegerField(), default=list, blank=True,
        help_text="Jours (0 = lundi … 6 = dimanche) dont le déjeuner reprend le dîner de la veille",
    )  # fmt: skip
    min_repeat_days = models.PositiveSmallIntegerField("répétition minimale (jours)", default=14)
    vegetarian_per_week = models.PositiveSmallIntegerField(
        "repas végétariens par semaine", default=2
    )
    source_mode = models.CharField(
        max_length=10, choices=SourceMode.choices, default=SourceMode.CLASSIC
    )
    cookeo_share = models.PositiveSmallIntegerField(
        "part de Cookeo (%)", default=50, validators=[MaxValueValidator(100)]
    )
    weights = models.JSONField(default=dict, blank=True, validators=[validate_weights])
    # Ordre des rayons choisi par le foyer (vide : parcours de magasin type).
    aisle_order = ArrayField(models.CharField(max_length=20), default=list, blank=True)
    # Styles de cuisine du foyer : influencent le menu sans jamais exclure une recette.
    liked_cuisines = ArrayField(
        models.CharField(max_length=20, choices=Cuisine.choices), default=list, blank=True
    )
    avoided_cuisines = ArrayField(
        models.CharField(max_length=20, choices=Cuisine.choices), default=list, blank=True
    )
    spice_tolerance = models.PositiveSmallIntegerField(
        "tolérance au piment", default=1, validators=[MaxValueValidator(3)]
    )
    exoticism = models.PositiveSmallIntegerField(
        "goût pour les cuisines d'ailleurs", default=1, validators=[MaxValueValidator(2)]
    )
    onboarded_at = models.DateTimeField(
        null=True, blank=True
    )  # assistant d'accueil terminé ou passé

    def __str__(self) -> str:
        return f"Réglages de {self.household}"


class TastePreference(models.Model):
    """Goût d'un convive pour un ingrédient (de -2 « déteste » à +2 « adore »)."""

    diner = models.ForeignKey(Diner, on_delete=models.CASCADE, related_name="tastes")
    ingredient = models.ForeignKey("catalog.Ingredient", on_delete=models.CASCADE, related_name="+")
    score = models.SmallIntegerField(validators=[MinValueValidator(-2), MaxValueValidator(2)])

    objects = RestrictionQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["diner", "ingredient"], name="taste_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.diner} : {self.ingredient} ({self.score})"
