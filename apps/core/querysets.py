"""Filtrage par foyer : unique point d'accès aux données privées (SPEC section 4)."""

from django.db import models


class HouseholdQuerySet(models.QuerySet):
    """`for_household` est le seul moyen autorisé de lire une donnée privée dans une vue."""

    household_field = "household"

    def for_household(self, household) -> "HouseholdQuerySet":
        return self.filter(**{self.household_field: household})
