import uuid

from django.db import models

from apps.core.querysets import HouseholdQuerySet
from apps.core.reference import Aisle


class ShoppingListQuerySet(HouseholdQuerySet):
    household_field = "plan__household"


class ShoppingList(models.Model):
    """Liste de courses d'un menu ; régénérable sans perdre cases cochées ni ajouts manuels."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.OneToOneField(
        "planner.MenuPlan", on_delete=models.CASCADE, related_name="shopping_list"
    )
    signature = models.CharField(max_length=64, blank=True)  # empreinte du menu au dernier calcul
    updated_at = models.DateTimeField(auto_now=True)

    objects = ShoppingListQuerySet.as_manager()

    def __str__(self) -> str:
        return f"Courses du {self.plan.start_date}"


class ItemQuerySet(HouseholdQuerySet):
    household_field = "shopping_list__plan__household"


class ShoppingItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shopping_list = models.ForeignKey(ShoppingList, on_delete=models.CASCADE, related_name="items")
    key = models.CharField(max_length=120)  # stable d'un calcul à l'autre ; « manual:<uuid> » sinon
    label = models.CharField(max_length=200)
    ingredient = models.ForeignKey(
        "catalog.Ingredient", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    quantity = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=20, blank=True)
    aisle = models.CharField(max_length=20, choices=Aisle.choices, default=Aisle.MISC)
    checked = models.BooleanField(default=False)
    checked_at = models.DateTimeField(null=True, blank=True)  # heure du dernier geste (synchro)
    hidden = models.BooleanField(default=False)  # retirée à la main : ne revient pas au recalcul
    optional = models.BooleanField(default=False)
    manual = models.BooleanField(default=False)
    recipes = models.JSONField(default=list, blank=True)  # [[id, titre], …]
    packs = models.PositiveSmallIntegerField(null=True, blank=True)
    pack_size = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    pack_label = models.CharField(max_length=20, blank=True)

    objects = ItemQuerySet.as_manager()

    class Meta:
        ordering = ["label"]
        constraints = [
            models.UniqueConstraint(
                fields=["shopping_list", "key"], name="shopping_item_key_unique"
            ),
        ]

    def __str__(self) -> str:
        return self.label


class PantryItem(models.Model):
    """Placard du foyer : produit toujours en stock, ou quantité disponible à déduire."""

    household = models.ForeignKey(
        "households.Household", on_delete=models.CASCADE, related_name="pantry"
    )
    ingredient = models.ForeignKey("catalog.Ingredient", on_delete=models.CASCADE, related_name="+")
    always_in_stock = models.BooleanField(default=True)
    quantity = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=20, blank=True)

    objects = HouseholdQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["household", "ingredient"], name="pantry_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.household} : {self.ingredient}"
