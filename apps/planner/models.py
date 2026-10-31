import uuid

from django.db import models

from apps.core.querysets import HouseholdQuerySet
from apps.core.reference import MealType


class SlotQuerySet(HouseholdQuerySet):
    household_field = "plan__household"


class MenuPlan(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "En cours"
        ARCHIVED = "archived", "Archivé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    household = models.ForeignKey(
        "households.Household", on_delete=models.CASCADE, related_name="menu_plans"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    params = models.JSONField(default=dict)  # paramètres figés de la demande
    seed = models.BigIntegerField()  # même graine, mêmes données : même menu
    created_at = models.DateTimeField(auto_now_add=True)

    objects = HouseholdQuerySet.as_manager()

    class Meta:
        ordering = ["-start_date", "-created_at"]
        indexes = [
            models.Index(fields=["household", "-start_date"], name="plan_household_start_idx")
        ]

    def __str__(self) -> str:
        return f"Menu du {self.start_date} au {self.end_date}"


class MenuSlot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(MenuPlan, on_delete=models.CASCADE, related_name="slots")
    day = models.DateField()
    meal_type = models.CharField(max_length=10, choices=MealType.choices)
    recipe = models.ForeignKey(
        "catalog.Recipe", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    servings = models.PositiveSmallIntegerField(default=4)
    locked = models.BooleanField(default=False)
    out_of_home = models.BooleanField(default=False)
    leftover = models.BooleanField(default=False)
    extra_guests = models.PositiveSmallIntegerField(default=0)
    note = models.CharField(max_length=300, blank=True)
    explanation = models.CharField(max_length=400, blank=True)

    objects = SlotQuerySet.as_manager()

    class Meta:
        ordering = ["day", "meal_type"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "day", "meal_type"], name="slot_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.day} {self.meal_type}"

    @property
    def key(self) -> str:
        return f"{self.day.isoformat()}:{self.meal_type}"
