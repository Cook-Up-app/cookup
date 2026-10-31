from datetime import date

from django import forms

from apps.core.reference import Equipment, MealType
from apps.households.models import Diner, HouseholdSettings

from .engine.types import COOKEO_CAPACITY
from .services import MAX_DAYS, PlanRequest

SOURCE_MODES = HouseholdSettings.SourceMode


class PlanForm(forms.Form):
    start_date = forms.DateField(
        label="Premier jour",
        # Les navigateurs n'acceptent que le format ISO dans un champ de type « date ».
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    days = forms.IntegerField(label="Nombre de jours", min_value=1, max_value=MAX_DAYS, initial=7)
    meals = forms.MultipleChoiceField(
        label="Repas à planifier", choices=MealType.choices, widget=forms.CheckboxSelectMultiple
    )
    diners = forms.ModelMultipleChoiceField(
        label="Convives présents",
        queryset=Diner.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    guests = forms.IntegerField(label="Invités ponctuels", min_value=0, max_value=20, initial=0)
    mode = forms.ChoiceField(
        label="Source des recettes", choices=SOURCE_MODES.choices, widget=forms.RadioSelect
    )
    cookeo_share = forms.IntegerField(
        label="Part de Cookeo (%) en mode mixte",
        min_value=0,
        max_value=100,
        initial=50,
        widget=forms.NumberInput(attrs={"type": "range", "min": 0, "max": 100, "step": 5}),
    )
    split_cookeo = forms.BooleanField(
        label="Scinder la cuisson Cookeo au-delà de 6 portions", required=False
    )
    quick = forms.BooleanField(label="Rapide (30 min maximum)", required=False)
    without_equipment = forms.MultipleChoiceField(
        label="Sans…",
        choices=Equipment.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    wanted_tags = forms.CharField(label="Envie de… (ex. soupe)", required=False, max_length=100)

    def __init__(self, *args, household, has_cookeo: bool, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.has_cookeo = has_cookeo
        # Les convives proposés (et acceptés) sont ceux du foyer, jamais d'un autre.
        self.fields["diners"].queryset = Diner.objects.for_household(household)

    def clean_start_date(self) -> date:
        return self.cleaned_data["start_date"]

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("mode")
        if mode and mode != SOURCE_MODES.CLASSIC:
            if not self.has_cookeo:
                self.add_error("mode", "Le mode Cookeo exige l'équipement Cookeo dans le foyer.")
            else:
                self._check_capacity(cleaned)
        return cleaned

    def _check_capacity(self, cleaned) -> None:
        """Cuve de 6 L : au-delà de 6 portions, on prévient et on propose de scinder."""
        people = len(cleaned.get("diners") or []) + (cleaned.get("guests") or 0)
        if people > COOKEO_CAPACITY and not cleaned.get("split_cookeo"):
            self.add_error(
                "mode",
                f"Le Cookeo contient {COOKEO_CAPACITY} portions au maximum et vous avez {people} "
                "convives : réduisez le nombre de convives, passez en mode Classique ou cochez "
                "« Scinder la cuisson Cookeo ».",
            )

    def to_request(self) -> PlanRequest:
        from datetime import timedelta

        data = self.cleaned_data
        start = data["start_date"]
        tags = tuple(t.strip().lower() for t in data["wanted_tags"].split(",") if t.strip())
        return PlanRequest(
            start_date=start,
            end_date=start + timedelta(days=data["days"] - 1),
            meals=tuple(data["meals"]),
            diner_ids=tuple(str(d.pk) for d in data["diners"]),
            guests=data["guests"],
            mode=data["mode"],
            cookeo_share=data["cookeo_share"],
            quick=data["quick"],
            split_cookeo=data["split_cookeo"],
            without_equipment=tuple(data["without_equipment"]),
            wanted_tags=tags,
        )
