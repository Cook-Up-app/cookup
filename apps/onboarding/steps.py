"""Étapes de l'assistant d'accueil : une question par écran, enregistrée tout de suite.

Ajouter une étape = écrire une classe décorée par `@step(...)` ; l'ordre est celui de `ORDER`.
"""

from dataclasses import dataclass
from typing import ClassVar

from apps.core.reference import Allergen
from apps.households import services as household_services
from apps.households.models import (
    Diner,
    DinerRestriction,
    Equipment,
    HouseholdEquipment,
    HouseholdSettings,
    TastePreference,
)

from . import forms

LIKE_SCORE, DISLIKE_SCORE = 2, -2
STRICT = DinerRestriction.Severity.STRICT_ALLERGY


@dataclass(frozen=True)
class StepRef:
    """Une étape à un endroit précis de la séquence (avec le convive concerné, le cas échéant)."""

    slug: str
    diner: Diner | None = None

    @property
    def key(self) -> str | None:
        return str(self.diner.pk) if self.diner else None


class Step:
    """Contrat d'une étape : sa question, son formulaire et ce qu'elle enregistre."""

    slug: ClassVar[str]
    question: ClassVar[str]
    help: ClassVar[str] = ""
    per_diner: ClassVar[bool] = False
    kind: ClassVar[str] = "form"  # « form », « diners » ou « summary » : choisit le gabarit

    def form(self, household, diner, data=None):
        raise NotImplementedError

    def save(self, household, diner, form) -> None:
        raise NotImplementedError

    def title(self, diner: Diner | None) -> str:
        return self.question.format(name=diner.first_name if diner else "")


REGISTRY: dict[str, Step] = {}


def step(cls: type[Step]) -> type[Step]:
    REGISTRY[cls.slug] = cls()
    return cls


def _settings(household) -> HouseholdSettings:
    return HouseholdSettings.objects.get_or_create(household=household)[0]


@step
class FoyerStep(Step):
    slug = "foyer"
    question = "Comment s'appelle votre foyer ?"
    help = "Juste un nom pour vous y retrouver, par exemple « Chez les Martin »."

    def form(self, household, diner, data=None):
        return forms.NameForm(data, initial={"name": household.name})

    def save(self, household, diner, form) -> None:
        household.name = form.cleaned_data["name"]
        household.save(update_fields=["name"])


@step
class ServingsStep(Step):
    slug = "portions"
    question = "Pour combien de personnes cuisinez-vous d'habitude ?"
    help = "Les recettes seront mises à l'échelle. Vous pourrez l'ajuster à chaque menu."

    def form(self, household, diner, data=None):
        return forms.ServingsForm(data, initial={"servings": str(household.default_servings)})

    def save(self, household, diner, form) -> None:
        household.default_servings = int(form.cleaned_data["servings"])
        household.save(update_fields=["default_servings"])


@step
class DinersStep(Step):
    slug = "convives"
    question = "Qui mange à table ?"
    help = "Ajoutez chaque personne, avec ou sans compte : ses allergies et ses goûts guideront les menus."
    kind = "diners"

    def form(self, household, diner, data=None):
        return forms.DinerAddForm(data, initial={"age_group": Diner.AgeGroup.ADULT})

    def save(self, household, diner, form) -> None:
        person = form.save(commit=False)
        person.household = household
        person.save()


@step
class AllergiesStep(Step):
    slug = "allergies"
    question = "{name} a-t-il des allergies ?"
    help = "Une allergie déclarée est une exclusion totale : aucune recette qui la contient ne sera proposée. Ne cochez rien s'il n'y en a pas."
    per_diner = True

    def form(self, household, diner, data=None):
        current = diner.restrictions.filter(severity=STRICT).exclude(allergen="")
        return forms.AllergiesForm(data, initial={"allergens": [r.allergen for r in current]})

    def save(self, household, diner, form) -> None:
        wanted = set(form.cleaned_data["allergens"])
        strict = diner.restrictions.filter(severity=STRICT).exclude(allergen="")
        strict.exclude(allergen__in=wanted).delete()
        have = set(strict.values_list("allergen", flat=True))
        DinerRestriction.objects.bulk_create(
            DinerRestriction(diner=diner, allergen=code, severity=STRICT) for code in wanted - have
        )


@step
class DietsStep(Step):
    slug = "regimes"
    question = "{name} suit-il un régime particulier ?"
    help = "Végétarien, sans porc, halal… Ne cochez rien si ce n'est pas le cas."
    per_diner = True

    def form(self, household, diner, data=None):
        return forms.DietsForm(data, initial={"diets": diner.diets})

    def save(self, household, diner, form) -> None:
        diner.diets = form.cleaned_data["diets"]
        diner.save(update_fields=["diets"])


@step
class EquipmentStep(Step):
    slug = "equipements"
    question = "De quoi disposez-vous en cuisine ?"
    help = "Seules les recettes réalisables avec votre matériel seront proposées. Cochez le Cookeo pour activer le mode Cookeo."

    def form(self, household, diner, data=None):
        owned = HouseholdEquipment.objects.filter(household=household).values_list(
            "equipment_id", flat=True
        )
        return forms.EquipmentStepForm(data, initial={"equipment": list(owned)})

    def save(self, household, diner, form) -> None:
        household_services.set_equipment(household, form.cleaned_data["equipment"])


@step
class MealsStep(Step):
    slug = "repas"
    question = "Quels repas voulez-vous planifier ?"
    help = "Vous pourrez changer ce choix à chaque nouveau menu."

    def form(self, household, diner, data=None):
        return forms.MealsForm(data, initial={"meals": _settings(household).meals})

    def save(self, household, diner, form) -> None:
        settings = _settings(household)
        settings.meals = form.cleaned_data["meals"]
        settings.save(update_fields=["meals"])


@step
class WeekdayTimeStep(Step):
    slug = "temps-semaine"
    question = "Combien de temps pour cuisiner en semaine ?"
    help = "Préparation et cuisson comprises : les recettes plus longues seront écartées."

    def form(self, household, diner, data=None):
        initial = str(_settings(household).max_minutes_weekday)
        return forms.WeekdayMinutesForm(data, initial={"minutes": initial})

    def save(self, household, diner, form) -> None:
        settings = _settings(household)
        settings.max_minutes_weekday = int(form.cleaned_data["minutes"])
        settings.save(update_fields=["max_minutes_weekday"])


@step
class WeekendTimeStep(Step):
    slug = "temps-weekend"
    question = "Et le week-end ?"
    help = "On peut se permettre des plats plus longs quand on a le temps."

    def form(self, household, diner, data=None):
        initial = str(_settings(household).max_minutes_weekend)
        return forms.WeekendMinutesForm(data, initial={"minutes": initial})

    def save(self, household, diner, form) -> None:
        settings = _settings(household)
        settings.max_minutes_weekend = int(form.cleaned_data["minutes"])
        settings.save(update_fields=["max_minutes_weekend"])


@step
class BudgetStep(Step):
    slug = "budget"
    question = "Quel budget pour les repas ?"
    help = "Une indication : les recettes plus coûteuses seront moins souvent proposées."

    def form(self, household, diner, data=None):
        return forms.BudgetForm(data, initial={"budget": str(_settings(household).budget_level)})

    def save(self, household, diner, form) -> None:
        settings = _settings(household)
        settings.budget_level = int(form.cleaned_data["budget"])
        settings.save(update_fields=["budget_level"])


@step
class LeftoversStep(Step):
    slug = "restes"
    question = "Y a-t-il des jours « restes » ?"
    help = "Le déjeuner de ces jours reprend le dîner de la veille, cuisiné en double portion. Ne cochez rien pour cuisiner à chaque repas."

    def form(self, household, diner, data=None):
        days = [str(d) for d in _settings(household).leftover_weekdays]
        return forms.LeftoversForm(data, initial={"days": days})

    def save(self, household, diner, form) -> None:
        settings = _settings(household)
        settings.leftover_weekdays = [int(d) for d in form.cleaned_data["days"]]
        settings.save(update_fields=["leftover_weekdays"])


@step
class TastesStep(Step):
    slug = "gouts"
    question = "Qu'aime {name} ?"
    help = "Facultatif : quelques goûts pour des menus plus justes. Vos notes de recettes affineront ensuite tout cela."
    per_diner = True

    def form(self, household, diner, data=None):
        form = forms.TastesForm(data)
        current = dict(
            TastePreference.objects.filter(diner=diner).values_list("ingredient_id", "score")
        )
        for ingredient in form.ingredients:
            score = current.get(ingredient.pk, 0)
            form.fields[f"i{ingredient.pk}"].initial = (
                forms.TASTE_LIKE
                if score > 0
                else forms.TASTE_DISLIKE
                if score < 0
                else forms.TASTE_NEUTRAL
            )
        return form

    def save(self, household, diner, form) -> None:
        choices = form.choices()
        TastePreference.objects.filter(diner=diner, ingredient__in=list(choices)).delete()
        scores = {forms.TASTE_LIKE: LIKE_SCORE, forms.TASTE_DISLIKE: DISLIKE_SCORE}
        TastePreference.objects.bulk_create(
            TastePreference(diner=diner, ingredient=ingredient, score=scores[choice])
            for ingredient, choice in choices.items()
            if choice in scores
        )


@step
class DoneStep(Step):
    slug = "fin"
    question = "Tout est prêt !"
    help = "Voici ce que nous avons retenu. Tout reste modifiable depuis « Plus »."
    kind = "summary"

    def form(self, household, diner, data=None):
        return None

    def save(self, household, diner, form) -> None:
        return None


ORDER = (
    "foyer", "portions", "convives", "allergies", "regimes", "equipements", "repas",
    "temps-semaine", "temps-weekend", "budget", "restes", "gouts", "fin",
)  # fmt: skip


def sequence(household) -> list[StepRef]:
    """Toutes les étapes dans l'ordre ; les étapes « par convive » se répètent pour chacun."""
    diners = list(Diner.objects.for_household(household).order_by("first_name"))
    refs: list[StepRef] = []
    for slug in ORDER:
        if REGISTRY[slug].per_diner:
            refs.extend(StepRef(slug, diner) for diner in diners)
        else:
            refs.append(StepRef(slug))
    return refs


def summary(household) -> list[tuple[str, str]]:
    """Récapitulatif lisible de ce qui a été configuré."""
    settings = _settings(household)
    diners = Diner.objects.for_household(household)
    equipment = Equipment.objects.filter(
        pk__in=HouseholdEquipment.objects.filter(household=household).values("equipment_id")
    )
    allergens = {
        str(Allergen(code).label)
        for code in DinerRestriction.objects.for_household(household)
        .filter(severity=STRICT)
        .exclude(allergen="")
        .values_list("allergen", flat=True)
    }
    return [
        ("Foyer", f"{household.name}, {household.default_servings} portions"),
        ("Convives", ", ".join(d.first_name for d in diners) or "aucun pour le moment"),
        ("Allergies", ", ".join(sorted(allergens)) or "aucune"),
        ("Équipements", ", ".join(e.label for e in equipment) or "aucun"),
        ("Temps", f"{settings.max_minutes_weekday} min en semaine, {settings.max_minutes_weekend} min le week-end"),
        ("Budget", {1: "économique", 2: "raisonnable", 3: "confortable"}[settings.budget_level]),
    ]  # fmt: skip
