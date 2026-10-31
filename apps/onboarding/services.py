from django.utils import timezone

from apps.catalog.models import RecipeFeedback
from apps.households.models import Diner, HouseholdEquipment, HouseholdSettings
from apps.planner.models import MenuPlan


def needs_onboarding(household) -> bool:
    """Vrai pour un foyer tout neuf : ni assistant terminé, ni convive, ni équipement, ni menu.

    Un foyer qui sert déjà (données saisies avant l'assistant) n'est jamais renvoyé dedans.
    """
    settings = HouseholdSettings.objects.filter(household=household).first()
    if settings and settings.onboarded_at:
        return False
    in_use = (
        Diner.objects.filter(household=household).exists()
        or HouseholdEquipment.objects.filter(household=household).exists()
        or MenuPlan.objects.filter(household=household).exists()
        or RecipeFeedback.objects.filter(household=household).exists()
    )
    return not in_use


def mark_onboarded(household) -> None:
    settings, _ = HouseholdSettings.objects.get_or_create(household=household)
    settings.onboarded_at = timezone.now()
    settings.save(update_fields=["onboarded_at"])


def restart(household) -> None:
    HouseholdSettings.objects.filter(household=household).update(onboarded_at=None)
