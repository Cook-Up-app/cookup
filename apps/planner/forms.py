from datetime import date

from django import forms

from apps.core.reference import Equipment, MealType
from apps.households.models import Diner, HouseholdSettings

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
    mode = forms.ChoiceField(label="Source des recettes", choices=SOURCE_MODES.choices)
    cookeo_share = forms.IntegerField(
        label="Part de Cookeo (%) en mode mixte", min_value=0, max_value=100, initial=50
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
        if cleaned.get("mode") != SOURCE_MODES.CLASSIC and not self.has_cookeo:
            self.add_error("mode", "Le mode Cookeo exige l'équipement Cookeo dans le foyer.")
        return cleaned

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
            without_equipment=tuple(data["without_equipment"]),
            wanted_tags=tags,
        )
