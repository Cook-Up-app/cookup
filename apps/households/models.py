import uuid

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from apps.core.querysets import HouseholdQuerySet
from apps.core.reference import Allergen, Diet


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
    ingredient_name = models.CharField("autre ingrédient", max_length=100, blank=True)
    severity = models.CharField(
        max_length=20, choices=Severity.choices, default=Severity.STRICT_ALLERGY
    )

    objects = RestrictionQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(allergen="") | ~Q(ingredient_name=""),
                name="restriction_has_target",
            ),
        ]

    def __str__(self) -> str:
        return self.allergen or self.ingredient_name


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
