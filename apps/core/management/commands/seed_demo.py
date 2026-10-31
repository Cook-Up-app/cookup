"""Données de démonstration pour le développement et les captures d'écran (jamais en production)."""

from datetime import timedelta

from allauth.mfa.models import Authenticator
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Ingredient, Recipe, RecipeFeedback
from apps.core.dev import DEMO_ACCOUNTS
from apps.households import services as household_services
from apps.households.models import (
    Diner,
    DinerRestriction,
    HouseholdEquipment,
    HouseholdSettings,
    Membership,
    TastePreference,
)
from apps.planner import services as planner_services
from apps.shopping import services as shopping_services

PASSWORD = "Demo-passw0rd-2026"  # noqa: S105 - compte de démonstration local
HOUSEHOLD_NAME = "Chez les Martin"


class Command(BaseCommand):
    help = "Crée des comptes, un foyer, un menu et une liste de courses de démonstration."

    def handle(self, *args, **options) -> None:
        if not settings.DEBUG:
            raise CommandError("Réservé au développement (DEBUG doit être vrai).")
        call_command("seed_catalog", verbosity=0)
        User.objects.filter(email__in=DEMO_ACCOUNTS.values()).delete()
        owner = self._user("proprietaire", "Camille Martin", with_mfa=True)
        member = self._user("membre", "Alex Martin", with_mfa=False)
        self._user("nouveau", "Nouvelle personne", with_mfa=True)
        household = self._household(owner, member)
        self._menu(household)
        self.stdout.write(
            f"Comptes : {', '.join(DEMO_ACCOUNTS.values())} (mot de passe : {PASSWORD})"
        )

    def _user(self, role: str, name: str, *, with_mfa: bool) -> User:
        user = User.objects.create_user(DEMO_ACCOUNTS[role], PASSWORD, display_name=name)
        if with_mfa:  # le propriétaire doit avoir une MFA pour passer la politique d'accès
            Authenticator.objects.create(user=user, type="totp", data={"secret": "demo"})
        return user

    def _household(self, owner: User, member: User):
        household_services.create_household(owner, HOUSEHOLD_NAME)
        household = Membership.objects.get(user=owner).household
        Membership.objects.create(user=member, household=household)
        for code in ("hob", "oven", "blender", "microwave", "cookeo_yy5449fb"):
            HouseholdEquipment.objects.create(household=household, equipment_id=code)
        HouseholdSettings.objects.create(household=household, leftover_weekdays=[6])
        lea = Diner.objects.create(household=household, first_name="Léa", age_group="child")
        Diner.objects.create(household=household, first_name="Camille")
        tom = Diner.objects.create(household=household, first_name="Tom", diets=["vegetarian"])
        DinerRestriction.objects.create(diner=lea, allergen="tree_nuts")
        for name, score in (("poulet", 2), ("carotte", -2)):
            TastePreference.objects.create(
                diner=lea, ingredient=Ingredient.objects.get(name=name), score=score
            )
        RecipeFeedback.objects.create(
            household=household,
            recipe=Recipe.objects.get(title="Gratin de courgettes"),
            favorite=True,
        )
        RecipeFeedback.objects.create(
            household=household, recipe=Recipe.objects.get(title="Curry de pois chiches"), rating=5
        )
        del tom
        return household

    def _menu(self, household) -> None:
        today = timezone.localdate()
        request = planner_services.PlanRequest(
            start_date=today,
            end_date=today + timedelta(days=6),
            meals=("lunch", "dinner"),
            diner_ids=tuple(str(d.pk) for d in household.diners.all()),
            mode="mixed",
            cookeo_share=30,
        )
        plan = planner_services.create_plan(household, request, today, seed=2026)
        shopping_list = shopping_services.sync_list(plan)
        for item in shopping_list.items.all()[:4]:
            shopping_services.toggle_checked(item)
